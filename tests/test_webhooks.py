from __future__ import annotations


def _first_economy_flight_id(client) -> int:
    flights = client.get("/api/v1/flights/search", params={"seat_class": "economy", "limit": 1}).json()
    return flights[0]["id"]


class TestWebhookSearchFlights:
    def test_search_returns_results(self, client):
        resp = client.post("/api/v1/webhooks/search-flights", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] > 0

    def test_search_by_destination(self, client):
        resp = client.post("/api/v1/webhooks/search-flights", json={"destination": "Athens"})
        assert resp.status_code == 200
        flights = resp.json()["flights"]
        assert all("Athens" in f["destination"] or "ATH" in f["destination"] for f in flights)

    def test_search_invalid_params_still_returns_success(self, client):
        # Graceful handling — unknown seat_class treated as no filter by the service
        resp = client.post("/api/v1/webhooks/search-flights", json={"destination": "Nowhere"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestWebhookBookFlight:
    def test_book_and_get(self, client):
        flight_id = _first_economy_flight_id(client)
        resp = client.post("/api/v1/webhooks/book-flight", json={
            "flight_id": flight_id,
            "passenger_name": "Webhook Tester",
            "passenger_email": "wh@example.com",
            "seat_preference": "aisle",
            "seat_class": "economy",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        ref = data["reference"]

        # Verify via get-booking webhook
        get_resp = client.post("/api/v1/webhooks/get-booking", json={"reference": ref})
        assert get_resp.status_code == 200
        assert get_resp.json()["reference"] == ref

    def test_book_nonexistent_flight_returns_error(self, client):
        resp = client.post("/api/v1/webhooks/book-flight", json={
            "flight_id": 999999,
            "passenger_name": "Ghost",
            "passenger_email": "ghost@example.com",
            "seat_class": "economy",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is False


class TestWebhookCancelReschedule:
    def test_cancel_via_webhook(self, client):
        flight_id = _first_economy_flight_id(client)
        ref = client.post("/api/v1/webhooks/book-flight", json={
            "flight_id": flight_id,
            "passenger_name": "Cancel Me",
            "passenger_email": "cancel@example.com",
            "seat_class": "economy",
        }).json()["reference"]

        resp = client.post("/api/v1/webhooks/cancel-booking", json={"reference": ref})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["status"] == "cancelled"


class TestWebhookQueryKnowledge:
    def test_valid_topic(self, client):
        resp = client.post("/api/v1/webhooks/query-knowledge", json={"topic": "pet_policy"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_invalid_topic_returns_error_gracefully(self, client):
        resp = client.post("/api/v1/webhooks/query-knowledge", json={"topic": "unknown_topic"})
        assert resp.status_code == 200
        assert resp.json()["success"] is False


class TestWebhookAddExtras:
    def test_add_extra_bag(self, client):
        flight_id = _first_economy_flight_id(client)
        ref = client.post("/api/v1/webhooks/book-flight", json={
            "flight_id": flight_id,
            "passenger_name": "Extra Bag Person",
            "passenger_email": "extras@example.com",
            "seat_class": "economy",
        }).json()["reference"]

        resp = client.post("/api/v1/webhooks/add-extras", json={
            "reference": ref,
            "checked_bags": 2,
            "special_items": ["bicycle"],
            "special_assistance": "",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["extras"]["checked_bags"] == 2
        assert "bicycle" in data["extras"]["special_items"]
