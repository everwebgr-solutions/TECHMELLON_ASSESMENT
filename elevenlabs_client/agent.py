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


def _webhook_tools(base_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """Define the tools (webhooks) available to the ElevenLabs agent."""
    base = base_url or API_BASE_URL

    return [
        {
            "type": "webhook",
            "name": "search_flights",
            "description": "Search available flights by destination, date, seat class, or price. Call this when the customer wants to find or book a flight.",
            "api_schema": {
                "url": f"{base}/api/v1/webhooks/search-flights",
                "method": "POST",
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "destination": {"type": "string", "description": "Destination city or airport code"},
                        "date": {"type": "string", "description": "Exact date in YYYY-MM-DD format"},
                        "date_to": {"type": "string", "description": "Upper bound date in YYYY-MM-DD format. Use with sort_by=price to find cheapest flights within a date range (e.g. set to today+7 days to search within the next week)"},
                        "seat_class": {"type": "string", "description": "Cabin class: economy, business, or first"},
                        "max_price_gbp": {"type": "number", "description": "Maximum price in GBP"},
                        "sort_by": {"type": "string", "description": "Sort by: price or departure"},
                        "limit": {"type": "integer", "description": "Max results to return"},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "webhook",
            "name": "book_flight",
            "description": "Book a specific flight for a customer. Always confirm flight details and price with the customer before calling this.",
            "api_schema": {
                "url": f"{base}/api/v1/webhooks/book-flight",
                "method": "POST",
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "flight_id": {"type": "integer", "description": "The ID of the flight to book"},
                        "passenger_name": {"type": "string", "description": "Full name of the passenger"},
                        "passenger_email": {"type": "string", "description": "Email address for the booking confirmation"},
                        "seat_preference": {"type": "string", "description": "Seat preference: window, aisle, extra_legroom, or none"},
                        "seat_class": {"type": "string", "description": "Cabin class: economy, business, or first"},
                    },
                    "required": ["flight_id", "passenger_name", "passenger_email", "seat_class"],
                },
            },
        },
        {
            "type": "webhook",
            "name": "get_booking",
            "description": "Retrieve an existing booking by reference number (e.g. BK-A1B2C3). Call this to look up booking details before making changes.",
            "api_schema": {
                "url": f"{base}/api/v1/webhooks/get-booking",
                "method": "POST",
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "reference": {"type": "string", "description": "Booking reference like BK-A1B2C3"},
                    },
                    "required": ["reference"],
                },
            },
        },
        {
            "type": "webhook",
            "name": "cancel_booking",
            "description": "Cancel an existing booking. Always confirm with the customer before cancelling.",
            "api_schema": {
                "url": f"{base}/api/v1/webhooks/cancel-booking",
                "method": "POST",
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "reference": {"type": "string", "description": "Booking reference to cancel"},
                    },
                    "required": ["reference"],
                },
            },
        },
        {
            "type": "webhook",
            "name": "reschedule_booking",
            "description": "Move an existing booking to a different flight. Requires finding a new flight first.",
            "api_schema": {
                "url": f"{base}/api/v1/webhooks/reschedule-booking",
                "method": "POST",
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "reference": {"type": "string", "description": "Existing booking reference"},
                        "new_flight_id": {"type": "integer", "description": "ID of the new flight"},
                    },
                    "required": ["reference", "new_flight_id"],
                },
            },
        },
        {
            "type": "webhook",
            "name": "add_extras",
            "description": "Add extra checked bags, special items (pram, bicycle, sports equipment), or special assistance to a booking.",
            "api_schema": {
                "url": f"{base}/api/v1/webhooks/add-extras",
                "method": "POST",
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "reference": {"type": "string", "description": "Booking reference"},
                        "checked_bags": {"type": "integer", "description": "Number of extra checked bags at £35 each"},
                        "special_items": {"type": "array", "items": {"type": "string", "description": "A special item name e.g. pram, bicycle, ski equipment"}, "description": "Special items e.g. pram, bicycle, ski equipment"},
                        "special_assistance": {"type": "string", "description": "Special assistance needed e.g. wheelchair, visual impairment"},
                    },
                    "required": ["reference"],
                },
            },
        },
        {
            "type": "webhook",
            "name": "query_knowledge",
            "description": "Look up airline policies. Use this for questions about pets, baggage, check-in times, cancellation, refunds, and special assistance.",
            "api_schema": {
                "url": f"{base}/api/v1/webhooks/query-knowledge",
                "method": "POST",
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Policy topic: pet_policy, baggage_allowance, special_assistance, check_in_windows, or cancellation_refund_policy",
                        },
                    },
                    "required": ["topic"],
                },
            },
        },
        {
            "type": "webhook",
            "name": "flight_status",
            "description": "Look up the scheduled status of a specific flight by flight number (e.g. AX101). Use this when a customer asks whether their flight is on time, what time it departs or arrives, or wants to check the status of a specific flight.",
            "api_schema": {
                "url": f"{base}/api/v1/webhooks/flight-status",
                "method": "POST",
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "flight_number": {"type": "string", "description": "Flight number e.g. AX101"},
                    },
                    "required": ["flight_number"],
                },
            },
        },
    ]


def _agent_config(system_prompt: str, base_url: Optional[str] = None) -> Dict[str, Any]:
    tts: Dict[str, Any] = {}
    if ELEVENLABS_VOICE_ID:
        tts["voice_id"] = ELEVENLABS_VOICE_ID

    config: Dict[str, Any] = {
        "name": "Sky Airways Customer Service",
        "conversation_config": {
            "agent": {
                "prompt": {
                    "prompt": system_prompt,
                    "tools": _webhook_tools(base_url),
                },
                "first_message": "Thank you for calling Sky Airways customer service. My name is Sky, and I'm here to help you today. How can I assist you?",
                "language": "en",
            },
        },
    }
    if tts:
        config["conversation_config"]["tts"] = tts
    return config


def create_agent(system_prompt: str, base_url: Optional[str] = None) -> str:
    """Create a new ElevenLabs agent and return its agent_id."""
    resp = httpx.post(
        f"{ELEVENLABS_BASE_URL}/convai/agents/create",
        headers=_HEADERS,
        json=_agent_config(system_prompt, base_url=base_url),
        timeout=30.0,
    )
    resp.raise_for_status()
    agent_id = resp.json()["agent_id"]
    return agent_id


def update_agent_prompt(agent_id: str, new_prompt: str) -> None:
    """Push an updated system prompt to an existing agent.

    Only the prompt text is patched — tools are created at agent-creation time
    via POST and cannot be updated inline via PATCH.
    """
    resp = httpx.patch(
        f"{ELEVENLABS_BASE_URL}/convai/agents/{agent_id}",
        headers=_HEADERS,
        json={
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": new_prompt,
                    }
                }
            }
        },
        timeout=30.0,
    )
    resp.raise_for_status()


def update_agent_tools(agent_id: str, base_url: str) -> str:
    """Ensure the agent's webhook tools point at base_url. Returns the agent_id to use.

    ElevenLabs PATCH for tools fails when internal tool library documents are
    stale, and creates orphaned library entries as a side effect. To avoid this,
    we compare the current tool URLs against base_url: if they already match we
    skip entirely; if they don't we delete the agent and recreate it cleanly with
    the correct URLs. The new agent_id is written back to .env.
    """
    import re
    from pathlib import Path

    agent_data = get_agent(agent_id)
    current_tools = (
        agent_data.get("conversation_config", {})
        .get("agent", {})
        .get("prompt", {})
        .get("tools", [])
    )

    # Check whether any tool URL already uses the desired base_url.
    if current_tools:
        first_url = current_tools[0].get("api_schema", {}).get("url", "")
        if first_url.startswith(base_url.rstrip("/")):
            return agent_id  # Already pointing at the right tunnel — nothing to do.

    # URLs are stale or no tools attached — recreate the agent with correct URLs.
    # Preserve whatever prompt is currently on the agent.
    current_prompt = (
        agent_data.get("conversation_config", {})
        .get("agent", {})
        .get("prompt", {})
        .get("prompt", "")
    )

    delete_agent(agent_id)
    new_id = create_agent(current_prompt, base_url=base_url)

    # Write new agent_id back to .env so future runs pick it up.
    env_path = Path(".env")
    if env_path.exists():
        content = env_path.read_text()
        content = re.sub(
            r"^ELEVENLABS_AGENT_ID=.*$",
            f"ELEVENLABS_AGENT_ID={new_id}",
            content,
            flags=re.MULTILINE,
        )
        env_path.write_text(content)

    return new_id


def delete_agent(agent_id: str) -> None:
    """Delete an existing ElevenLabs agent."""
    resp = httpx.delete(
        f"{ELEVENLABS_BASE_URL}/convai/agents/{agent_id}",
        headers=_HEADERS,
        timeout=15.0,
    )
    # 404 is fine — agent may already be gone
    if resp.status_code not in (200, 204, 404):
        resp.raise_for_status()


def recreate_agent(agent_id: str, system_prompt: str, base_url: str) -> str:
    """
    Delete the existing agent and create a fresh one with updated webhook URLs.
    Returns the new agent_id.
    """
    delete_agent(agent_id)
    return create_agent(system_prompt, base_url=base_url)


def get_agent(agent_id: str) -> Dict[str, Any]:
    """Fetch the current agent configuration."""
    resp = httpx.get(
        f"{ELEVENLABS_BASE_URL}/convai/agents/{agent_id}",
        headers=_HEADERS,
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()
