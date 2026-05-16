"""
Conversation simulator.

Uses ElevenLabs' simulate-conversation endpoint to run a full conversation
server-side. ElevenLabs plays both sides: the airline agent (configured via
its system prompt and tools) and a simulated customer (driven by our scenario
prompt). The full transcript is returned in one API call.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

# Delay between emitting turns so the UI shows messages one-by-one
# rather than all at once (the ElevenLabs API returns the full transcript in one call)
_TURN_EMIT_DELAY = 0.4

from config import MAX_CONVERSATION_TURNS
from elevenlabs_client.chat import simulate_full_conversation
from refinement.scenarios import Scenario

_CUSTOMER_SYSTEM_PROMPT_TEMPLATE = """\
You are roleplaying as a customer calling Sky Airways customer service.

Your goal: {customer_brief}

Rules:
- Stay in character as a real customer at all times
- Respond naturally and conversationally (1-3 sentences per turn)
- Provide any personal details the agent needs (use realistic fictional values)
- If your goal is fully achieved, say "Perfect, thank you so much" and end the call
- If the agent cannot help after 3 attempts, politely give up and say goodbye
- Do NOT play both sides of the conversation
- Do NOT explain what you are doing in brackets
- Output ONLY what the customer would say
"""


def simulate_conversation(
    agent_id: str,
    scenario: Scenario,
    on_turn: Optional[Callable[[str, str], None]] = None,
) -> List[Dict[str, str]]:
    """
    Run a full simulated conversation for a given scenario.

    ElevenLabs handles the full conversation server-side. We supply a
    customer prompt; ElevenLabs runs the agent + simulated user and returns
    the complete transcript.

    Args:
        agent_id: ElevenLabs agent ID
        scenario: Customer scenario to simulate
        on_turn: Optional callback(role, content) for real-time streaming

    Returns:
        Transcript as list of {role, content, timestamp} dicts
    """
    customer_prompt = _CUSTOMER_SYSTEM_PROMPT_TEMPLATE.format(
        customer_brief=scenario["customer_brief"]
    )

    raw_transcript = simulate_full_conversation(
        agent_id=agent_id,
        customer_prompt=customer_prompt,
        max_turns=MAX_CONVERSATION_TURNS,
    )

    transcript: List[Dict[str, str]] = []
    for turn in raw_transcript:
        role = turn.get("role", "unknown")
        message = turn.get("message") or ""
        if not message:
            continue
        entry: Dict[str, str] = {
            "role": role,
            "content": message,
            "timestamp": str(turn.get("time_in_call_secs", 0)),
        }
        transcript.append(entry)
        if on_turn:
            on_turn(role, message)
            time.sleep(_TURN_EMIT_DELAY)

    return transcript
