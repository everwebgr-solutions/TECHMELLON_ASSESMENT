from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class FlightOut(BaseModel):
    id: int
    flight_number: str
    origin: str
    destination: str
    departure_dt: datetime
    arrival_dt: datetime
    seat_class: Literal["economy", "business", "first"]
    price_gbp: float
    total_seats: int
    available_seats: int

    model_config = {"from_attributes": True}


class FlightSearchParams(BaseModel):
    destination: Optional[str] = Field(None, description="Partial or full destination name/code")
    date: Optional[str] = Field(None, description="ISO date string YYYY-MM-DD — exact date filter")
    date_to: Optional[str] = Field(None, description="ISO date string YYYY-MM-DD — upper bound (inclusive)")
    seat_class: Optional[Literal["economy", "business", "first"]] = None
    max_price_gbp: Optional[float] = None
    sort_by: Literal["price", "departure"] = "departure"
    limit: int = Field(20, ge=1, le=100)
