from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.db import Base


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    reference: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    flight_id: Mapped[int] = mapped_column(Integer, ForeignKey("flights.id"), nullable=False)
    passenger_name: Mapped[str] = mapped_column(String(200), nullable=False)
    passenger_email: Mapped[str] = mapped_column(String(254), nullable=False)
    seat_preference: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    seat_class: Mapped[str] = mapped_column(String(20), nullable=False)
    _extras: Mapped[str] = mapped_column("extras", Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="confirmed")
    total_price_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    @property
    def extras(self) -> dict:
        return json.loads(self._extras)

    @extras.setter
    def extras(self, value: dict) -> None:
        self._extras = json.dumps(value)

    def __repr__(self) -> str:
        return f"<Booking {self.reference} flight_id={self.flight_id} status={self.status}>"
