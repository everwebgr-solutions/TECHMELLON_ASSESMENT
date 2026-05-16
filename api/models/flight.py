from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.db import Base


class Flight(Base):
    __tablename__ = "flights"
    __table_args__ = (
        CheckConstraint("available_seats >= 0", name="ck_available_seats_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    flight_number: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    origin: Mapped[str] = mapped_column(String(100), nullable=False)
    destination: Mapped[str] = mapped_column(String(100), nullable=False)
    departure_dt: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    arrival_dt: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    seat_class: Mapped[str] = mapped_column(String(20), nullable=False)  # economy | business | first
    price_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    total_seats: Mapped[int] = mapped_column(Integer, nullable=False)
    available_seats: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Flight {self.flight_number} {self.origin}→{self.destination} {self.departure_dt.date()} {self.seat_class}>"
