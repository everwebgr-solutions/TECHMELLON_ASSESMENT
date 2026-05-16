from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.db import get_db
from api.schemas.flight import FlightOut, FlightSearchParams
from api.services.flight_service import get_flight, search_flights

router = APIRouter(prefix="/flights", tags=["flights"])


@router.get("/search", response_model=list[FlightOut])
def search(params: FlightSearchParams = Depends(), db: Session = Depends(get_db)):
    return search_flights(db, params)


@router.get("/{flight_id}", response_model=FlightOut)
def get_one(flight_id: int, db: Session = Depends(get_db)):
    flight = get_flight(db, flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail=f"Flight {flight_id} not found")
    return flight
