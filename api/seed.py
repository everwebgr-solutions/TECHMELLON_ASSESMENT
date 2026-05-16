"""
Seed the flight database with realistic fictional data.
Generates flights across 7 days from today, 6 destinations, 3 seat classes.

Run: python -m api.seed
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from itertools import product

from api.db import Base, SessionLocal, engine
from api.models.flight import Flight

DESTINATIONS = [
    ("London Heathrow", "LHR"),
    ("Paris Charles de Gaulle", "CDG"),
    ("Amsterdam Schiphol", "AMS"),
    ("Barcelona El Prat", "BCN"),
    ("Rome Fiumicino", "FCO"),
    ("Athens Eleftherios Venizelos", "ATH"),
]

ORIGIN = "Dublin International"
ORIGIN_CODE = "DUB"

# (class, multiplier, total_seats)
SEAT_CLASSES = [
    ("economy", 1.0, 120),
    ("business", 2.8, 24),
    ("first", 5.5, 8),
]

# Base prices per destination (economy GBP)
BASE_PRICES = {
    "LHR": 89,
    "CDG": 119,
    "AMS": 109,
    "BCN": 149,
    "FCO": 169,
    "ATH": 199,
}

# Departure slots (hour, minute)
DEPARTURE_SLOTS = [
    (6, 30),
    (9, 0),
    (12, 15),
    (15, 45),
    (18, 0),
    (20, 30),
]

# Flight durations in hours
DURATIONS = {
    "LHR": 1.5,
    "CDG": 2.25,
    "AMS": 2.0,
    "BCN": 2.75,
    "FCO": 3.0,
    "ATH": 3.75,
}


def _flight_number(dest_code: str, day_offset: int, slot_idx: int, class_letter: str) -> str:
    return f"AX{dest_code}{day_offset}{slot_idx}{class_letter}"


def generate_flights(days: int = 7) -> list[Flight]:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    flights: list[Flight] = []
    counter = 100

    for day_offset, (dest_name, dest_code), (slot_hour, slot_min) in product(
        range(days), DESTINATIONS, DEPARTURE_SLOTS
    ):
        dep_dt = today + timedelta(days=day_offset, hours=slot_hour, minutes=slot_min)
        duration_h = DURATIONS[dest_code]
        arr_dt = dep_dt + timedelta(hours=duration_h)

        base_price = BASE_PRICES[dest_code]

        for seat_class, multiplier, total_seats in SEAT_CLASSES:
            price = round(base_price * multiplier, 2)
            fn = f"AX{counter}"
            counter += 1

            flights.append(
                Flight(
                    flight_number=fn,
                    origin=f"{ORIGIN} ({ORIGIN_CODE})",
                    destination=f"{dest_name} ({dest_code})",
                    departure_dt=dep_dt.replace(tzinfo=None),  # store as naive UTC
                    arrival_dt=arr_dt.replace(tzinfo=None),
                    seat_class=seat_class,
                    price_gbp=price,
                    total_seats=total_seats,
                    available_seats=total_seats,
                )
            )

    return flights


def seed(drop_existing: bool = False) -> None:
    if drop_existing:
        Base.metadata.drop_all(bind=engine)
        print("Dropped all tables.")

    Base.metadata.create_all(bind=engine)
    print("Tables created.")

    with SessionLocal() as session:
        existing = session.query(Flight).count()
        if existing > 0:
            print(f"Database already has {existing} flights — skipping seed.")
            return

        flights = generate_flights(days=7)
        session.add_all(flights)
        session.commit()
        print(f"Seeded {len(flights)} flights across 7 days, 6 destinations, 3 classes.")


if __name__ == "__main__":
    drop = "--drop" in sys.argv
    seed(drop_existing=drop)
