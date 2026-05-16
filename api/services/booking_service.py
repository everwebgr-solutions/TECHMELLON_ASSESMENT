from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models.booking import Booking
from api.models.flight import Flight
from api.schemas.booking import BookingCreate, BookingExtrasUpdate, BookingReschedule


def _generate_reference() -> str:
    """Produce a short booking reference like BK-A1B2C3."""
    return "BK-" + uuid.uuid4().hex[:6].upper()


def create_booking(db: Session, payload: BookingCreate) -> Booking:
    """
    Create a booking with seat reservation.
    Uses a SELECT FOR UPDATE pattern via with_for_update() to prevent double-booking
    under concurrent requests.
    """
    flight = (
        db.execute(
            select(Flight).where(Flight.id == payload.flight_id).with_for_update()
        )
        .scalars()
        .first()
    )

    if flight is None:
        raise ValueError(f"Flight {payload.flight_id} not found")

    if flight.seat_class != payload.seat_class:
        raise ValueError(
            f"Flight {flight.flight_number} offers {flight.seat_class} class, "
            f"not {payload.seat_class}"
        )

    if flight.available_seats <= 0:
        raise ValueError(
            f"No seats available on flight {flight.flight_number} ({flight.seat_class})"
        )

    flight.available_seats -= 1

    booking = Booking(
        reference=_generate_reference(),
        flight_id=flight.id,
        passenger_name=payload.passenger_name,
        passenger_email=payload.passenger_email,
        seat_preference=payload.seat_preference,
        seat_class=payload.seat_class,
        status="confirmed",
        total_price_gbp=flight.price_gbp,
    )
    booking.extras = {"checked_bags": 0, "special_items": [], "special_assistance": ""}

    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def get_booking(db: Session, reference: str) -> Optional[Booking]:
    return db.query(Booking).filter(Booking.reference == reference).first()


def cancel_booking(db: Session, reference: str) -> Booking:
    booking = get_booking(db, reference)
    if booking is None:
        raise ValueError(f"Booking {reference} not found")
    if booking.status == "cancelled":
        raise ValueError(f"Booking {reference} is already cancelled")

    booking.status = "cancelled"

    # Return the seat to the flight
    flight = db.query(Flight).filter(Flight.id == booking.flight_id).first()
    if flight:
        flight.available_seats += 1

    db.commit()
    db.refresh(booking)
    return booking


def reschedule_booking(db: Session, reference: str, payload: BookingReschedule) -> Booking:
    booking = get_booking(db, reference)
    if booking is None:
        raise ValueError(f"Booking {reference} not found")
    if booking.status == "cancelled":
        raise ValueError(f"Cannot reschedule a cancelled booking ({reference})")
    if booking.flight_id == payload.new_flight_id:
        raise ValueError("New flight is the same as the current flight")

    # Reserve seat on new flight
    new_flight = (
        db.execute(
            select(Flight).where(Flight.id == payload.new_flight_id).with_for_update()
        )
        .scalars()
        .first()
    )
    if new_flight is None:
        raise ValueError(f"Flight {payload.new_flight_id} not found")
    if new_flight.seat_class != booking.seat_class:
        raise ValueError(
            f"New flight offers {new_flight.seat_class} class; "
            f"booking is for {booking.seat_class} class"
        )
    if new_flight.available_seats <= 0:
        raise ValueError(f"No seats available on flight {new_flight.flight_number}")

    # Release seat on old flight
    old_flight = db.query(Flight).filter(Flight.id == booking.flight_id).first()
    if old_flight:
        old_flight.available_seats += 1

    new_flight.available_seats -= 1
    booking.flight_id = new_flight.id
    booking.total_price_gbp = new_flight.price_gbp

    db.commit()
    db.refresh(booking)
    return booking


def add_extras(db: Session, reference: str, payload: BookingExtrasUpdate) -> Booking:
    booking = get_booking(db, reference)
    if booking is None:
        raise ValueError(f"Booking {reference} not found")
    if booking.status == "cancelled":
        raise ValueError(f"Cannot add extras to a cancelled booking ({reference})")

    current = booking.extras
    current["checked_bags"] = payload.checked_bags
    if payload.special_items:
        current["special_items"] = list(set(current.get("special_items", []) + payload.special_items))
    if payload.special_assistance:
        current["special_assistance"] = payload.special_assistance

    # Extra bag fee: £35 each (knowledge-base consistent)
    extra_bag_fee = payload.checked_bags * 35.0
    booking.extras = current
    booking.total_price_gbp += extra_bag_fee

    db.commit()
    db.refresh(booking)
    return booking
