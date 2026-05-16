from __future__ import annotations

import pytest


VALID_TOPICS = [
    "pet_policy",
    "baggage_allowance",
    "special_assistance",
    "check_in_windows",
    "cancellation_refund_policy",
]


@pytest.mark.parametrize("topic", VALID_TOPICS)
def test_valid_topic_returns_200(client, topic):
    resp = client.get(f"/api/v1/knowledge/{topic}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["topic"] == topic
    assert "content" in data


def test_invalid_topic_returns_404(client):
    resp = client.get("/api/v1/knowledge/nonexistent_topic")
    assert resp.status_code == 404


def test_topics_list_returns_all(client):
    resp = client.get("/api/v1/knowledge/topics")
    assert resp.status_code == 200
    topics = resp.json()["topics"]
    for expected in VALID_TOPICS:
        assert expected in topics


def test_pet_policy_has_required_fields(client):
    resp = client.get("/api/v1/knowledge/pet_policy")
    content = resp.json()["content"]
    assert "cabin_pets" in content
    assert "hold_pets" in content


def test_baggage_has_excess_fees(client):
    resp = client.get("/api/v1/knowledge/baggage_allowance")
    content = resp.json()["content"]
    assert "excess_and_additional_fees" in content
    fees = content["excess_and_additional_fees"]
    assert "extra_bag_fee_gbp" in fees
