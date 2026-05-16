"""
ElevenLabs webhook endpoints.
Each function maps 1-to-1 to a tool the ElevenLabs agent can call.
Input validation is strict (Pydantic); all business logic lives in services.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.db import get_db
from api.schemas.booking import BookingCreate, BookingExtrasUpdate, BookingReschedule
from api.schemas.flight import FlightSearchParams
from api.services import booking_service, flight_service
from knowledge_base import kb_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ── Tool call log ─────────────────────────────────────────────────────────────
# Records every webhook invocation during a simulation so the evaluator can
# see what tools were actually called, with what inputs, and whether they
# succeeded — rather than inferring this from conversation text alone.

_call_log: List[Dict[str, Any]] = []
_call_log_lock = threading.Lock()


def clear_call_log() -> None:
    with _call_log_lock:
        _call_log.clear()


def get_call_log() -> List[Dict[str, Any]]:
    with _call_log_lock:
        return list(_call_log)


def _log_call(tool: str, inputs: Dict[str, Any], result: Dict[str, Any]) -> None:
    entry = {
        "tool": tool,
        "inputs": inputs,
        "success": result.get("success", True),
        "constraint": result.get("constraint", False),
        "error": result.get("error"),
        "reference": result.get("reference"),  # booking reference from book_flight on success
    }
    with _call_log_lock:
        _call_log.append(entry)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ok(data: dict) -> dict:
    return {"success": True, **data}


def _err(message: str) -> dict:
    return {"success": False, "error": message}


def _constraint(message: str) -> dict:
    """Expected business outcome (not found, already cancelled, no seats, etc.).
    The backend worked correctly — this is not a code bug.
    The agent receives the same error structure so it can tell the customer,
    but the log marks it as a constraint rather than a failure."""
    return {"success": False, "error": message, "constraint": True}


# ── Webhook request/response models ──────────────────────────────────────────

class SearchFlightsRequest(BaseModel):
    destination: Optional[str] = None
    date: Optional[str] = Field(None, description="YYYY-MM-DD exact date")
    date_to: Optional[str] = Field(None, description="YYYY-MM-DD upper bound (use with sort_by=price to find cheapest within a date range)")
    seat_class: Optional[str] = None
    max_price_gbp: Optional[float] = None
    sort_by: str = "departure"
    limit: int = Field(10, ge=1, le=50)


class FlightStatusRequest(BaseModel):
    flight_number: str


class BookFlightRequest(BaseModel):
    flight_id: int
    passenger_name: str
    passenger_email: str
    seat_preference: str = "none"
    seat_class: str


class GetBookingRequest(BaseModel):
    reference: str


class CancelBookingRequest(BaseModel):
    reference: str


class RescheduleBookingRequest(BaseModel):
    reference: str
    new_flight_id: int


class AddExtrasRequest(BaseModel):
    reference: str
    checked_bags: int = 0
    special_items: List[str] = Field(default_factory=list)
    special_assistance: str = ""


class QueryKnowledgeRequest(BaseModel):
    topic: str = Field(..., description="One of: pet_policy, baggage_allowance, special_assistance, check_in_windows, cancellation_refund_policy")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/search-flights")
def webhook_search_flights(req: SearchFlightsRequest, db: Session = Depends(get_db)):
    inputs = {k: v for k, v in req.model_dump().items() if v is not None and v != "departure" and v != 10}
    try:
        params = FlightSearchParams(
            destination=req.destination,
            date=req.date,
            date_to=req.date_to,
            seat_class=req.seat_class,
            max_price_gbp=req.max_price_gbp,
            sort_by=req.sort_by,
            limit=req.limit,
        )
        flights = flight_service.search_flights(db, params)
        result = _ok({
            "count": len(flights),
            "flights": [
                {
                    "id": f.id,
                    "flight_number": f.flight_number,
                    "origin": f.origin,
                    "destination": f.destination,
                    "departure_dt": f.departure_dt.isoformat(),
                    "arrival_dt": f.arrival_dt.isoformat(),
                    "seat_class": f.seat_class,
                    "price_gbp": f.price_gbp,
                    "available_seats": f.available_seats,
                }
                for f in flights
            ],
        })
        _log_call("search_flights", inputs, {"success": True, "count": len(flights)})
        return result
    except ValueError as exc:
        result = _constraint(str(exc))
        _log_call("search_flights", inputs, result)
        return result
    except Exception as exc:
        result = _err(str(exc))
        _log_call("search_flights", inputs, result)
        return result


@router.post("/book-flight")
def webhook_book_flight(req: BookFlightRequest, db: Session = Depends(get_db)):
    inputs = {"flight_id": req.flight_id, "passenger_name": req.passenger_name, "seat_class": req.seat_class, "seat_preference": req.seat_preference}
    try:
        payload = BookingCreate(
            flight_id=req.flight_id,
            passenger_name=req.passenger_name,
            passenger_email=req.passenger_email,
            seat_preference=req.seat_preference,
            seat_class=req.seat_class,
        )
        booking = booking_service.create_booking(db, payload)
        result = _ok({
            "reference": booking.reference,
            "flight_id": booking.flight_id,
            "passenger_name": booking.passenger_name,
            "seat_class": booking.seat_class,
            "seat_preference": booking.seat_preference,
            "total_price_gbp": booking.total_price_gbp,
            "status": booking.status,
            "message": (
                f"Booking confirmed. You MUST read the booking reference to the customer: {booking.reference}. "
                "They will need this reference for any future changes, cancellations, or extras."
            ),
        })
        _log_call("book_flight", inputs, {"success": True, "reference": booking.reference})
        return result
    except ValueError as exc:
        result = _constraint(str(exc))
        _log_call("book_flight", inputs, result)
        return result
    except Exception as exc:
        result = _err(f"System error: {str(exc)}")
        _log_call("book_flight", inputs, result)
        return result


@router.post("/get-booking")
def webhook_get_booking(req: GetBookingRequest, db: Session = Depends(get_db)):
    booking = booking_service.get_booking(db, req.reference.upper())
    if not booking:
        result = _err(f"Booking {req.reference} not found")
        _log_call("get_booking", {"reference": req.reference}, result)
        return result
    flight = flight_service.get_flight(db, booking.flight_id)
    result = _ok({
        "reference": booking.reference,
        "status": booking.status,
        "passenger_name": booking.passenger_name,
        "passenger_email": booking.passenger_email,
        "seat_class": booking.seat_class,
        "seat_preference": booking.seat_preference,
        "extras": booking.extras,
        "total_price_gbp": booking.total_price_gbp,
        "flight": {
            "id": flight.id,
            "flight_number": flight.flight_number,
            "origin": flight.origin,
            "destination": flight.destination,
            "departure_dt": flight.departure_dt.isoformat(),
            "arrival_dt": flight.arrival_dt.isoformat(),
            "seat_class": flight.seat_class,
        } if flight else None,
    })
    _log_call("get_booking", {"reference": req.reference}, {"success": True, "status": booking.status})
    return result


@router.post("/cancel-booking")
def webhook_cancel_booking(req: CancelBookingRequest, db: Session = Depends(get_db)):
    try:
        booking = booking_service.cancel_booking(db, req.reference.upper())
        result = _ok({
            "reference": booking.reference,
            "status": booking.status,
            "message": f"Booking {booking.reference} has been successfully cancelled.",
        })
        _log_call("cancel_booking", {"reference": req.reference}, {"success": True})
        return result
    except ValueError as exc:
        result = _constraint(str(exc))
        _log_call("cancel_booking", {"reference": req.reference}, result)
        return result
    except Exception as exc:
        result = _err(str(exc))
        _log_call("cancel_booking", {"reference": req.reference}, result)
        return result


@router.post("/reschedule-booking")
def webhook_reschedule_booking(req: RescheduleBookingRequest, db: Session = Depends(get_db)):
    inputs = {"reference": req.reference, "new_flight_id": req.new_flight_id}
    try:
        payload = BookingReschedule(new_flight_id=req.new_flight_id)
        booking = booking_service.reschedule_booking(db, req.reference.upper(), payload)
        flight = flight_service.get_flight(db, booking.flight_id)
        result = _ok({
            "reference": booking.reference,
            "status": booking.status,
            "new_flight_id": booking.flight_id,
            "new_total_price_gbp": booking.total_price_gbp,
            "new_flight": {
                "flight_number": flight.flight_number,
                "destination": flight.destination,
                "departure_dt": flight.departure_dt.isoformat(),
            } if flight else None,
        })
        _log_call("reschedule_booking", inputs, {"success": True})
        return result
    except ValueError as exc:
        result = _constraint(str(exc))
        _log_call("reschedule_booking", inputs, result)
        return result
    except Exception as exc:
        result = _err(str(exc))
        _log_call("reschedule_booking", inputs, result)
        return result


@router.post("/add-extras")
def webhook_add_extras(req: AddExtrasRequest, db: Session = Depends(get_db)):
    inputs = {"reference": req.reference, "checked_bags": req.checked_bags, "special_items": req.special_items, "special_assistance": req.special_assistance}
    try:
        payload = BookingExtrasUpdate(
            checked_bags=req.checked_bags,
            special_items=req.special_items,
            special_assistance=req.special_assistance,
        )
        booking = booking_service.add_extras(db, req.reference.upper(), payload)
        result = _ok({
            "reference": booking.reference,
            "extras": booking.extras,
            "total_price_gbp": booking.total_price_gbp,
            "message": "Extras updated successfully.",
        })
        _log_call("add_extras", inputs, {"success": True})
        return result
    except ValueError as exc:
        result = _constraint(str(exc))
        _log_call("add_extras", inputs, result)
        return result
    except Exception as exc:
        result = _err(str(exc))
        _log_call("add_extras", inputs, result)
        return result


@router.post("/query-knowledge")
def webhook_query_knowledge(req: QueryKnowledgeRequest):
    section = kb_service.get(req.topic)
    if section is None:
        results = kb_service.search(req.topic)
        if results:
            result = _ok({"topic": req.topic, "content": results})
            _log_call("query_knowledge", {"topic": req.topic}, {"success": True})
            return result
        else:
            result = _err(f"Unknown topic '{req.topic}'. Available topics: {kb_service.list_topics()}")
            _log_call("query_knowledge", {"topic": req.topic}, result)
            return result
    _log_call("query_knowledge", {"topic": req.topic}, {"success": True})
    return _ok({"topic": req.topic, "content": section})


@router.post("/flight-status")
def webhook_flight_status(req: FlightStatusRequest, db: Session = Depends(get_db)):
    flight = flight_service.get_flight_by_number(db, req.flight_number)
    if not flight:
        result = _err(f"Flight {req.flight_number} not found")
        _log_call("flight_status", {"flight_number": req.flight_number}, result)
        return result
    from datetime import datetime
    now = datetime.utcnow()
    status = "departed" if flight.departure_dt < now else "scheduled"
    result = _ok({
        "flight_number": flight.flight_number,
        "origin": flight.origin,
        "destination": flight.destination,
        "departure_dt": flight.departure_dt.isoformat(),
        "arrival_dt": flight.arrival_dt.isoformat(),
        "seat_class": flight.seat_class,
        "status": status,
        "available_seats": flight.available_seats,
    })
    _log_call("flight_status", {"flight_number": req.flight_number}, {"success": True, "status": status})
    return result


# ── Tool call log endpoints (used by the refinement loop across process boundary) ──

@router.get("/tool-calls")
def get_tool_calls():
    """Return the recorded webhook call log for the current/last simulation."""
    return {"tool_calls": get_call_log()}


@router.delete("/tool-calls")
def clear_tool_calls():
    """Clear the call log. Called by the loop before each simulation starts."""
    clear_call_log()
    return {"cleared": True}