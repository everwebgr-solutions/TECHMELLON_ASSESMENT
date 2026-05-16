from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.models.flight import Flight
from api.schemas.flight import FlightSearchParams


def search_flights(db: Session, params: FlightSearchParams) -> List[Flight]:
    q = db.query(Flight).filter(
        Flight.available_seats > 0,
        Flight.departure_dt >= datetime.utcnow(),
    )

    if params.destination:
        term = f"%{params.destination.lower()}%"
        q = q.filter(func.lower(Flight.destination).like(term))

    if params.date:
        try:
            target: date = datetime.strptime(params.date, "%Y-%m-%d").date()
            q = q.filter(func.date(Flight.departure_dt) == target.isoformat())
        except ValueError:
            pass
    elif params.date_to:
        # date_to without date = open-ended range from now up to date_to (inclusive)
        try:
            upper: date = datetime.strptime(params.date_to, "%Y-%m-%d").date()
            q = q.filter(func.date(Flight.departure_dt) <= upper.isoformat())
        except ValueError:
            pass

    if params.seat_class:
        q = q.filter(Flight.seat_class == params.seat_class)

    if params.max_price_gbp is not None:
        q = q.filter(Flight.price_gbp <= params.max_price_gbp)

    if params.sort_by == "price":
        q = q.order_by(Flight.price_gbp.asc())
    else:
        q = q.order_by(Flight.departure_dt.asc())

    return q.limit(params.limit).all()


def get_flight(db: Session, flight_id: int) -> Optional[Flight]:
    return db.query(Flight).filter(Flight.id == flight_id).first()


def get_flight_by_number(db: Session, flight_number: str) -> Optional[Flight]:
    return (
        db.query(Flight)
        .filter(Flight.flight_number == flight_number.upper())
        .order_by(Flight.departure_dt.asc())
        .first()
    )


def cheapest_in_week(db: Session, destination: Optional[str] = None) -> List[Flight]:
    """Return the cheapest available flights within the next 7 days."""
    from datetime import timedelta
    upper = (datetime.utcnow() + timedelta(days=7)).date()
    params = FlightSearchParams(
        destination=destination,
        date_to=upper.isoformat(),
        sort_by="price",
        limit=20,
    )
    return search_flights(db, params)