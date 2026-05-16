from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class BookingCreate(BaseModel):
    flight_id: int
    passenger_name: str = Field(..., min_length=2, max_length=200)
    passenger_email: EmailStr
    seat_preference: Literal["window", "aisle", "extra_legroom", "none"] = "none"
    seat_class: Literal["economy", "business", "first"]


class BookingExtrasUpdate(BaseModel):
    checked_bags: int = Field(0, ge=0, le=5, description="Number of extra checked bags")
    special_items: List[str] = Field(
        default_factory=list,
        description="e.g. ['pram', 'bicycle', 'golf clubs', 'ski equipment']",
    )
    special_assistance: str = Field(
        "",
        description="e.g. 'wheelchair', 'visual impairment', 'deaf assistance'",
    )


class BookingReschedule(BaseModel):
    new_flight_id: int


class BookingOut(BaseModel):
    id: int
    reference: str
    flight_id: int
    passenger_name: str
    passenger_email: str
    seat_preference: str
    seat_class: str
    extras: Dict[str, Any]
    status: str
    total_price_gbp: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
