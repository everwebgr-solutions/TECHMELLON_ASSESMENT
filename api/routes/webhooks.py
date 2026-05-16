"""
ElevenLabs webhook endpoints.
Each function maps 1-to-1 to a tool the ElevenLabs agent can call.
Input validation is strict (Pydantic); all business logic lives in services.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.db import get_db
from api.schemas.booking import BookingCreate, BookingExtrasUpdate, BookingReschedule
from api.schemas.flight import FlightSearchParams
from api.services import booking_service, flight_service
from knowledge_base import kb_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ok(data: dict) -> dict:
    return {"success": True, **data}


def _err(message: str) -> dict:
    return {"success": False, "error": message}


# ── Webhook request/response models ──────────────────────────────────────────

class SearchFlightsRequest(BaseModel):
    destination: Optional[str] = None
    date: Optional[str] = Field(None, description="YYYY-MM-DD")
    seat_class: Optional[str] = None
    max_price_gbp: Optional[float] = None
    sort_by: str = "departure"
    limit: int = Field(10, ge=1, le=50)


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
    try:
        params = FlightSearchParams(
            destination=req.destination,
            date=req.date,
            seat_class=req.seat_class,
            max_price_gbp=req.max_price_gbp,
            sort_by=req.sort_by,
            limit=req.limit,
        )
        flights = flight_service.search_flights(db, params)
        return _ok({
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
    except Exception as exc:
        return _err(str(exc))


@router.post("/book-flight")
def webhook_book_flight(req: BookFlightRequest, db: Session = Depends(get_db)):
    try:
        payload = BookingCreate(
            flight_id=req.flight_id,
            passenger_name=req.passenger_name,
            passenger_email=req.passenger_email,
            seat_preference=req.seat_preference,
            seat_class=req.seat_class,
        )
        booking = booking_service.create_booking(db, payload)
        return _ok({
            "reference": booking.reference,
            "flight_id": booking.flight_id,
            "passenger_name": booking.passenger_name,
            "seat_class": booking.seat_class,
            "seat_preference": booking.seat_preference,
            "total_price_gbp": booking.total_price_gbp,
            "status": booking.status,
        })
    except Exception as exc:
        return _err(str(exc))


@router.post("/get-booking")
def webhook_get_booking(req: GetBookingRequest, db: Session = Depends(get_db)):
    booking = booking_service.get_booking(db, req.reference.upper())
    if not booking:
        return _err(f"Booking {req.reference} not found")
    flight = flight_service.get_flight(db, booking.flight_id)
    return _ok({
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


@router.post("/cancel-booking")
def webhook_cancel_booking(req: CancelBookingRequest, db: Session = Depends(get_db)):
    try:
        booking = booking_service.cancel_booking(db, req.reference.upper())
        return _ok({
            "reference": booking.reference,
            "status": booking.status,
            "message": f"Booking {booking.reference} has been successfully cancelled.",
        })
    except Exception as exc:
        return _err(str(exc))


@router.post("/reschedule-booking")
def webhook_reschedule_booking(req: RescheduleBookingRequest, db: Session = Depends(get_db)):
    try:
        payload = BookingReschedule(new_flight_id=req.new_flight_id)
        booking = booking_service.reschedule_booking(db, req.reference.upper(), payload)
        flight = flight_service.get_flight(db, booking.flight_id)
        return _ok({
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
    except Exception as exc:
        return _err(str(exc))


@router.post("/add-extras")
def webhook_add_extras(req: AddExtrasRequest, db: Session = Depends(get_db)):
    try:
        payload = BookingExtrasUpdate(
            checked_bags=req.checked_bags,
            special_items=req.special_items,
            special_assistance=req.special_assistance,
        )
        booking = booking_service.add_extras(db, req.reference.upper(), payload)
        return _ok({
            "reference": booking.reference,
            "extras": booking.extras,
            "total_price_gbp": booking.total_price_gbp,
            "message": "Extras updated successfully.",
        })
    except Exception as exc:
        return _err(str(exc))


@router.post("/query-knowledge")
def webhook_query_knowledge(req: QueryKnowledgeRequest):
    section = kb_service.get(req.topic)
    if section is None:
        # Try keyword search as fallback
        results = kb_service.search(req.topic)
        if results:
            return _ok({"topic": req.topic, "content": results})
        return _err(
            f"Unknown topic '{req.topic}'. Available topics: {kb_service.list_topics()}"
        )
    return _ok({"topic": req.topic, "content": section})
