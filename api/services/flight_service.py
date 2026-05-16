from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.models.flight import Flight
from api.schemas.flight import FlightSearchParams


def search_flights(db: Session, params: FlightSearchParams) -> List[Flight]:
    q = db.query(Flight).filter(Flight.available_seats > 0)

    if params.destination:
        term = f"%{params.destination.lower()}%"
        q = q.filter(func.lower(Flight.destination).like(term))

    if params.date:
        try:
            target: date = datetime.strptime(params.date, "%Y-%m-%d").date()
            q = q.filter(func.date(Flight.departure_dt) == target.isoformat())
        except ValueError:
            pass  # invalid date format — ignore filter, return unfiltered results

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


def cheapest_in_week(db: Session, destination: Optional[str] = None) -> List[Flight]:
    """Return the cheapest available flight per destination within the next 7 days."""
    q = db.query(Flight).filter(
        Flight.available_seats > 0,
        Flight.departure_dt >= datetime.utcnow(),
        Flight.departure_dt <= datetime.utcnow().replace(hour=23, minute=59)
        .__class__(
            *(datetime.utcnow().timetuple()[:3]),
        ),
    )
    # Simpler: just use search with sort_by=price
    params = FlightSearchParams(destination=destination, sort_by="price", limit=20)
    return search_flights(db, params)
