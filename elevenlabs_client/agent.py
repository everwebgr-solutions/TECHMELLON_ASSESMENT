"""
ElevenLabs agent management.
Creates or updates the airline customer service agent via the REST API.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from config import (
    API_BASE_URL,
    ELEVENLABS_AGENT_ID,
    ELEVENLABS_API_KEY,
    ELEVENLABS_BASE_URL,
    ELEVENLABS_VOICE_ID,
)

_HEADERS = {
    "xi-api-key": ELEVENLABS_API_KEY,
    "Content-Type": "application/json",
}


def _webhook_tools() -> List[Dict[str, Any]]:
    """Define the tools (webhooks) available to the ElevenLabs agent."""
    base = API_BASE_URL

    return [
        {
            "type": "webhook",
            "name": "search_flights",
            "description": "Search available flights by destination, date, seat class, or price. Call this when the customer wants to find or book a flight.",
            "url": f"{base}/api/v1/webhooks/search-flights",
            "method": "POST",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string", "description": "Destination city or airport code"},
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "seat_class": {"type": "string", "enum": ["economy", "business", "first"], "description": "Cabin class"},
                    "max_price_gbp": {"type": "number", "description": "Maximum price in GBP"},
                    "sort_by": {"type": "string", "enum": ["price", "departure"], "default": "departure"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": [],
            },
        },
        {
            "type": "webhook",
            "name": "book_flight",
            "description": "Book a specific flight for a customer. Always confirm flight details and price with the customer before calling this.",
            "url": f"{base}/api/v1/webhooks/book-flight",
            "method": "POST",
            "parameters": {
                "type": "object",
                "properties": {
                    "flight_id": {"type": "integer", "description": "The ID of the flight to book"},
                    "passenger_name": {"type": "string", "description": "Full name of the passenger"},
                    "passenger_email": {"type": "string", "description": "Email address for the booking confirmation"},
                    "seat_preference": {"type": "string", "enum": ["window", "aisle", "extra_legroom", "none"], "default": "none"},
                    "seat_class": {"type": "string", "enum": ["economy", "business", "first"]},
                },
                "required": ["flight_id", "passenger_name", "passenger_email", "seat_class"],
            },
        },
        {
            "type": "webhook",
            "name": "get_booking",
            "description": "Retrieve an existing booking by reference number (e.g. BK-A1B2C3). Call this to look up booking details before making changes.",
            "url": f"{base}/api/v1/webhooks/get-booking",
            "method": "POST",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string", "description": "Booking reference like BK-A1B2C3"},
                },
                "required": ["reference"],
            },
        },
        {
            "type": "webhook",
            "name": "cancel_booking",
            "description": "Cancel an existing booking. Always confirm with the customer before cancelling.",
            "url": f"{base}/api/v1/webhooks/cancel-booking",
            "method": "POST",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string"},
                },
                "required": ["reference"],
            },
        },
        {
            "type": "webhook",
            "name": "reschedule_booking",
            "description": "Move an existing booking to a different flight. Requires finding a new flight first.",
            "url": f"{base}/api/v1/webhooks/reschedule-booking",
            "method": "POST",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string", "description": "Existing booking reference"},
                    "new_flight_id": {"type": "integer", "description": "ID of the new flight"},
                },
                "required": ["reference", "new_flight_id"],
            },
        },
        {
            "type": "webhook",
            "name": "add_extras",
            "description": "Add extra checked bags, special items (pram, bicycle, sports equipment), or special assistance to a booking.",
            "url": f"{base}/api/v1/webhooks/add-extras",
            "method": "POST",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string"},
                    "checked_bags": {"type": "integer", "default": 0, "description": "Number of extra checked bags (£35 each)"},
                    "special_items": {"type": "array", "items": {"type": "string"}, "description": "e.g. ['pram', 'bicycle', 'ski equipment']"},
                    "special_assistance": {"type": "string", "description": "e.g. 'wheelchair', 'visual impairment'"},
                },
                "required": ["reference"],
            },
        },
        {
            "type": "webhook",
            "name": "query_knowledge",
            "description": "Look up airline policies. Use this for questions about pets, baggage, check-in times, cancellation, refunds, and special assistance.",
            "url": f"{base}/api/v1/webhooks/query-knowledge",
            "method": "POST",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "enum": [
                            "pet_policy",
                            "baggage_allowance",
                            "special_assistance",
                            "check_in_windows",
                            "cancellation_refund_policy",
                        ],
                        "description": "The policy topic to retrieve",
                    },
                },
                "required": ["topic"],
            },
        },
    ]


def _agent_config(system_prompt: str) -> Dict[str, Any]:
    return {
        "name": "Sky Airways Customer Service",
        "conversation_config": {
            "agent": {
                "prompt": {
                    "prompt": system_prompt,
                    "tools": _webhook_tools(),
                },
                "first_message": "Thank you for calling Sky Airways customer service. My name is Sky, and I'm here to help you today. How can I assist you?",
                "language": "en",
            },
            "tts": {
                "voice_id": ELEVENLABS_VOICE_ID,
            },
        },
    }


def create_agent(system_prompt: str) -> str:
    """Create a new ElevenLabs agent and return its agent_id."""
    resp = httpx.post(
        f"{ELEVENLABS_BASE_URL}/convai/agents/create",
        headers=_HEADERS,
        json=_agent_config(system_prompt),
        timeout=30.0,
    )
    resp.raise_for_status()
    agent_id = resp.json()["agent_id"]
    return agent_id


def update_agent_prompt(agent_id: str, new_prompt: str) -> None:
    """Push an updated system prompt to an existing ElevenLabs agent."""
    resp = httpx.patch(
        f"{ELEVENLABS_BASE_URL}/convai/agents/{agent_id}",
        headers=_HEADERS,
        json={
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": new_prompt,
                        "tools": _webhook_tools(),
                    }
                }
            }
        },
        timeout=30.0,
    )
    resp.raise_for_status()


def get_agent(agent_id: str) -> Dict[str, Any]:
    """Fetch the current agent configuration."""
    resp = httpx.get(
        f"{ELEVENLABS_BASE_URL}/convai/agents/{agent_id}",
        headers=_HEADERS,
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()
