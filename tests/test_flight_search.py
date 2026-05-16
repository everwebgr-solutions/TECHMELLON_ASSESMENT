from __future__ import annotations

from datetime import datetime, timedelta


def test_search_all_returns_results(client):
    resp = client.get("/api/v1/flights/search")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0


def test_search_by_destination(client):
    resp = client.get("/api/v1/flights/search", params={"destination": "Paris"})
    assert resp.status_code == 200
    flights = resp.json()
    assert all("Paris" in f["destination"] or "CDG" in f["destination"] for f in flights)


def test_search_by_seat_class(client):
    resp = client.get("/api/v1/flights/search", params={"seat_class": "business"})
    assert resp.status_code == 200
    flights = resp.json()
    assert all(f["seat_class"] == "business" for f in flights)


def test_search_by_max_price(client):
    resp = client.get("/api/v1/flights/search", params={"max_price_gbp": 100})
    assert resp.status_code == 200
    flights = resp.json()
    assert all(f["price_gbp"] <= 100 for f in flights)


def test_search_sort_by_price(client):
    resp = client.get("/api/v1/flights/search", params={"sort_by": "price", "limit": 20})
    assert resp.status_code == 200
    prices = [f["price_gbp"] for f in resp.json()]
    assert prices == sorted(prices)


def test_search_by_date_returns_only_that_day(client):
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    resp = client.get("/api/v1/flights/search", params={"date": tomorrow, "limit": 100})
    assert resp.status_code == 200
    flights = resp.json()
    if flights:
        for f in flights:
            assert f["departure_dt"].startswith(tomorrow)


def test_get_flight_by_id(client):
    flights = client.get("/api/v1/flights/search", params={"limit": 1}).json()
    flight_id = flights[0]["id"]
    resp = client.get(f"/api/v1/flights/{flight_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == flight_id


def test_get_nonexistent_flight_returns_404(client):
    resp = client.get("/api/v1/flights/999999")
    assert resp.status_code == 404
