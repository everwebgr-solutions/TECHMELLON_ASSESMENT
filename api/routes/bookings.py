from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.db import get_db
from api.schemas.booking import (
    BookingCreate,
    BookingExtrasUpdate,
    BookingOut,
    BookingReschedule,
)
from api.services.booking_service import (
    add_extras,
    cancel_booking,
    create_booking,
    get_booking,
    reschedule_booking,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("", response_model=BookingOut, status_code=201)
def book(payload: BookingCreate, db: Session = Depends(get_db)):
    try:
        return create_booking(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/{reference}", response_model=BookingOut)
def retrieve(reference: str, db: Session = Depends(get_db)):
    booking = get_booking(db, reference.upper())
    if not booking:
        raise HTTPException(status_code=404, detail=f"Booking {reference} not found")
    return booking


@router.post("/{reference}/cancel", response_model=BookingOut)
def cancel(reference: str, db: Session = Depends(get_db)):
    try:
        return cancel_booking(db, reference.upper())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/{reference}/reschedule", response_model=BookingOut)
def reschedule(reference: str, payload: BookingReschedule, db: Session = Depends(get_db)):
    try:
        return reschedule_booking(db, reference.upper(), payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/{reference}/extras", response_model=BookingOut)
def extras(reference: str, payload: BookingExtrasUpdate, db: Session = Depends(get_db)):
    try:
        return add_extras(db, reference.upper(), payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
