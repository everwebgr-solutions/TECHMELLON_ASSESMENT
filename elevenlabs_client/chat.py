"""
ElevenLabs Conversational AI — simulation driver.

Uses the /convai/agents/{agent_id}/simulate-conversation endpoint to run a
full text-mode conversation server-side. ElevenLabs handles both the agent
and a simulated user; the simulated user's behaviour is defined by the
customer_prompt we supply.

No audio, no WebSocket — purely REST.
"""
from __future__ import annotations

from typing import Any, Dict, List

import httpx

from config import ELEVENLABS_API_KEY, ELEVENLABS_BASE_URL, MAX_CONVERSATION_TURNS

_HEADERS = {
    "xi-api-key": ELEVENLABS_API_KEY,
    "Content-Type": "application/json",
}


def simulate_full_conversation(
    agent_id: str,
    customer_prompt: str,
    max_turns: int = MAX_CONVERSATION_TURNS,
) -> List[Dict[str, Any]]:
    """
    Run a full simulated conversation via ElevenLabs simulate-conversation API.

    ElevenLabs runs both sides of the conversation server-side:
    - The agent uses its configured system prompt + tools
    - The simulated user follows customer_prompt

    Returns the raw simulated_conversation list from the API response.
    Each entry has: role, message, tool_calls, tool_results, time_in_call_secs
    """
    resp = httpx.post(
        f"{ELEVENLABS_BASE_URL}/convai/agents/{agent_id}/simulate-conversation",
        headers=_HEADERS,
        json={
            "simulation_specification": {
                "simulated_user_config": {
                    "prompt": {"prompt": customer_prompt},
                }
            },
            "new_turns_limit": max_turns,
        },
        timeout=300.0,
    )
    resp.raise_for_status()
    return resp.json().get("simulated_conversation", [])
