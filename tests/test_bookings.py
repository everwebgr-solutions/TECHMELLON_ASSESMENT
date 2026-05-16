from __future__ import annotations

import pytest


def _first_economy_flight(client) -> dict:
    resp = client.get("/api/v1/flights/search", params={"seat_class": "economy", "limit": 1})
    assert resp.status_code == 200, resp.text
    flights = resp.json()
    assert flights, "No economy flights in test DB"
    return flights[0]


def _book(client, flight_id: int, email: str = "test@example.com", seat_class: str = "economy") -> dict:
    resp = client.post("/api/v1/bookings", json={
        "flight_id": flight_id,
        "passenger_name": "Test Passenger",
        "passenger_email": email,
        "seat_preference": "window",
        "seat_class": seat_class,
    })
    return resp


class TestCreateBooking:
    def test_creates_booking_successfully(self, client):
        flight = _first_economy_flight(client)
        resp = _book(client, flight["id"])
        assert resp.status_code == 201
        data = resp.json()
        assert data["reference"].startswith("BK-")
        assert data["status"] == "confirmed"
        assert data["flight_id"] == flight["id"]

    def test_booking_reduces_available_seats(self, client):
        flight = _first_economy_flight(client)
        before = flight["available_seats"]
        _book(client, flight["id"])
        after = client.get(f"/api/v1/flights/{flight['id']}").json()["available_seats"]
        assert after == before - 1

    def test_wrong_class_returns_409(self, client):
        # Get a business flight and try to book it as economy
        resp = client.get("/api/v1/flights/search", params={"seat_class": "business", "limit": 1})
        flight = resp.json()[0]
        r = _book(client, flight["id"], seat_class="economy")
        assert r.status_code == 409


class TestRetrieveBooking:
    def test_retrieve_by_reference(self, client):
        flight = _first_economy_flight(client)
        ref = _book(client, flight["id"]).json()["reference"]
        resp = client.get(f"/api/v1/bookings/{ref}")
        assert resp.status_code == 200
        assert resp.json()["reference"] == ref

    def test_lowercase_reference_normalised(self, client):
        flight = _first_economy_flight(client)
        ref = _book(client, flight["id"]).json()["reference"]
        resp = client.get(f"/api/v1/bookings/{ref.lower()}")
        assert resp.status_code == 200

    def test_nonexistent_reference_returns_404(self, client):
        resp = client.get("/api/v1/bookings/BK-ZZZZZZ")
        assert resp.status_code == 404


class TestCancelBooking:
    def test_cancel_changes_status(self, client):
        flight = _first_economy_flight(client)
        ref = _book(client, flight["id"]).json()["reference"]
        resp = client.post(f"/api/v1/bookings/{ref}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_restores_seat(self, client):
        flight = _first_economy_flight(client)
        seats_before = flight["available_seats"]
        ref = _book(client, flight["id"]).json()["reference"]
        client.post(f"/api/v1/bookings/{ref}/cancel")
        seats_after = client.get(f"/api/v1/flights/{flight['id']}").json()["available_seats"]
        assert seats_after == seats_before

    def test_double_cancel_returns_409(self, client):
        flight = _first_economy_flight(client)
        ref = _book(client, flight["id"]).json()["reference"]
        client.post(f"/api/v1/bookings/{ref}/cancel")
        resp = client.post(f"/api/v1/bookings/{ref}/cancel")
        assert resp.status_code == 409


class TestRescheduleBooking:
    def test_reschedule_changes_flight(self, client):
        flights = client.get(
            "/api/v1/flights/search", params={"seat_class": "economy", "limit": 5}
        ).json()
        assert len(flights) >= 2, "Need at least 2 economy flights for reschedule test"
        original_id = flights[0]["id"]
        new_id = flights[1]["id"]
        ref = _book(client, original_id).json()["reference"]
        resp = client.post(f"/api/v1/bookings/{ref}/reschedule", json={"new_flight_id": new_id})
        assert resp.status_code == 200
        assert resp.json()["flight_id"] == new_id


class TestAddExtras:
    def test_add_checked_bag(self, client):
        flight = _first_economy_flight(client)
        ref = _book(client, flight["id"]).json()["reference"]
        resp = client.post(f"/api/v1/bookings/{ref}/extras", json={
            "checked_bags": 1,
            "special_items": [],
            "special_assistance": "",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["extras"]["checked_bags"] == 1
        # £35 extra bag fee added to base price
        assert data["total_price_gbp"] > flight["price_gbp"]

    def test_add_special_item(self, client):
        flight = _first_economy_flight(client)
        ref = _book(client, flight["id"]).json()["reference"]
        resp = client.post(f"/api/v1/bookings/{ref}/extras", json={
            "checked_bags": 0,
            "special_items": ["pram"],
            "special_assistance": "",
        })
        assert resp.status_code == 200
        assert "pram" in resp.json()["extras"]["special_items"]
