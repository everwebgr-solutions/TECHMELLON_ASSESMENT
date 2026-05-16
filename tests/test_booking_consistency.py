"""
Booking consistency tests.

These verify the core invariant: available_seats never goes below zero and
no two bookings can claim the last seat. We test this at the service layer
(not via threads) because:
  - SQLite WAL + CHECK constraint enforce atomicity at the DB level
  - The service's with_for_update() + CHECK(available_seats >= 0) is what
    prevents over-booking; that logic is exercised here directly
  - Thread-based tests add OS scheduling non-determinism without testing
    more of the actual constraint code
"""
from __future__ import annotations

import pytest

from api.models.flight import Flight
from api.schemas.booking import BookingCreate
from api.services.booking_service import create_booking


def _payload(flight_id: int, i: int = 0) -> BookingCreate:
    return BookingCreate(
        flight_id=flight_id,
        passenger_name=f"Passenger {i}",
        passenger_email=f"passenger{i}@example.com",
        seat_preference="none",
        seat_class="economy",
    )


def test_seats_cannot_go_negative(db):
    """Book exactly available_seats times — next attempt must raise ValueError."""
    flight = db.query(Flight).filter(Flight.seat_class == "economy").first()
    assert flight is not None

    # Force exactly 2 seats available for a deterministic test
    flight.available_seats = 2
    db.commit()

    create_booking(db, _payload(flight.id, 1))
    create_booking(db, _payload(flight.id, 2))

    with pytest.raises(ValueError, match="No seats available"):
        create_booking(db, _payload(flight.id, 3))

    db.refresh(flight)
    assert flight.available_seats == 0


def test_booking_reduces_seat_count_by_one(db):
    """Each successful booking decrements available_seats by exactly 1."""
    flight = db.query(Flight).filter(Flight.seat_class == "economy").first()
    db.refresh(flight)
    before = flight.available_seats

    if before == 0:
        flight.available_seats = 5
        db.commit()
        before = 5

    create_booking(db, _payload(flight.id, 99))
    db.refresh(flight)
    assert flight.available_seats == before - 1


def test_cancel_restores_seat(db):
    """Cancelling a booking returns the seat to the flight."""
    from api.services.booking_service import cancel_booking

    flight = db.query(Flight).filter(Flight.seat_class == "economy").first()
    db.refresh(flight)
    if flight.available_seats == 0:
        flight.available_seats = 3
        db.commit()

    before = flight.available_seats
    booking = create_booking(db, _payload(flight.id, 50))
    cancel_booking(db, booking.reference)

    db.refresh(flight)
    assert flight.available_seats == before


def test_cannot_book_nonexistent_flight(db):
    with pytest.raises(ValueError, match="not found"):
        create_booking(db, _payload(flight_id=999999))


def test_class_mismatch_raises(db):
    """Trying to book economy on a business flight raises ValueError."""
    business_flight = db.query(Flight).filter(Flight.seat_class == "business").first()
    payload = BookingCreate(
        flight_id=business_flight.id,
        passenger_name="Mismatch Tester",
        passenger_email="mismatch@example.com",
        seat_preference="none",
        seat_class="economy",  # wrong class
    )
    with pytest.raises(ValueError, match="class"):
        create_booking(db, payload)
