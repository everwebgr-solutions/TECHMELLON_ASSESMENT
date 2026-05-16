"""
Conversation simulator.

Our LLM (LLM_SIMULATOR) plays the customer; ElevenLabs plays the agent
via Chat Mode WebSocket (text messages, audio discarded server-side).

Turn loop:
  1. LLM generates customer utterance from conversation history
  2. Sent to ElevenLabs via user_transcript WebSocket message
  3. Agent's text response received via agent_response event
     (ElevenLabs calls our webhook tools transparently during this step)
  4. Agent response appended to LLM history as the "user" message
  5. Repeat until customer signals done or MAX_CONVERSATION_TURNS reached
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Dict, List, Optional

from config import MAX_CONVERSATION_TURNS

# Total wall-clock budget for one simulated conversation.
# Prevents a single stuck session from blocking the refinement loop indefinitely.
_CONVERSATION_TIMEOUT = 300.0  # 5 minutes
from elevenlabs_client.chat import ChatSession
from llm.base import LLMMessage
from llm.router import get_provider
from refinement.scenarios import Scenario

logger = logging.getLogger(__name__)

_END_PHRASES = (
    "thank you so much",
    "goodbye",
    "good bye",
    "bye",
    "have a good",
    "take care",
    "thanks, bye",
    "that's all i needed",
    "that's everything",
)

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

_FIRST_TURN_PROMPT = (
    "The agent just answered the call. "
    "Start the conversation by stating your reason for calling."
)


def _is_conversation_over(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _END_PHRASES)


def _clean_llm_output(text: str) -> str:
    """Strip common LLM role prefixes the model sometimes prepends."""
    for prefix in ("Customer:", "customer:", "User:", "user:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    return text.strip()


async def _run_conversation(
    agent_id: str,
    scenario: Scenario,
    on_turn: Optional[Callable[[str, str], None]],
) -> List[Dict[str, str]]:
    llm = get_provider("simulator")
    system_prompt = _CUSTOMER_SYSTEM_PROMPT_TEMPLATE.format(
        customer_brief=scenario["customer_brief"]
    )

    session = ChatSession(agent_id)
    await session.connect()

    transcript: List[Dict[str, str]] = []
    # LLM sees: system prompt, then alternating user (=agent) / assistant (=customer)
    messages = [LLMMessage.system(system_prompt)]

    try:
        for turn_num in range(1, MAX_CONVERSATION_TURNS + 1):
            # ── Customer turn ─────────────────────────────────────────────────
            if turn_num == 1:
                messages.append(LLMMessage.user(_FIRST_TURN_PROMPT))

            raw_customer = llm.complete(messages)
            customer_text = _clean_llm_output(
                raw_customer if isinstance(raw_customer, str) else str(raw_customer)
            )

            transcript.append({
                "role": "user",
                "content": customer_text,
                "timestamp": str(turn_num),
            })
            if on_turn:
                on_turn("user", customer_text)
            logger.debug("[SIM] Customer (turn %d): %.80s", turn_num, customer_text)

            # End detection — don't send a goodbye to the agent
            if _is_conversation_over(customer_text):
                logger.info("[SIM] Customer ended conversation at turn %d", turn_num)
                break

            # ── Agent turn (ElevenLabs + our webhooks) ────────────────────────
            agent_text = await session.send(customer_text)

            transcript.append({
                "role": "agent",
                "content": agent_text,
                "timestamp": str(turn_num),
            })
            if on_turn:
                on_turn("agent", agent_text)
            logger.debug("[SIM] Agent (turn %d): %.80s", turn_num, agent_text)

            # Update LLM history: what the customer just said, then what the agent replied
            messages.append(LLMMessage.assistant(customer_text))
            messages.append(LLMMessage.user(
                f"Agent said: {agent_text}\n\nWhat do you say next as the customer?"
            ))

    finally:
        await session.close()

    return transcript


def simulate_conversation(
    agent_id: str,
    scenario: Scenario,
    on_turn: Optional[Callable[[str, str], None]] = None,
) -> List[Dict[str, str]]:
    """
    Run a full simulated conversation and return the transcript.

    Our LLM (LLM_SIMULATOR) drives the customer side turn-by-turn.
    ElevenLabs drives the agent side via Chat Mode WebSocket, calling
    our webhook tools transparently during each agent turn.

    Raises RuntimeError if the conversation exceeds _CONVERSATION_TIMEOUT.
    """
    async def _with_timeout() -> List[Dict[str, str]]:
        return await asyncio.wait_for(
            _run_conversation(agent_id, scenario, on_turn),
            timeout=_CONVERSATION_TIMEOUT,
        )

    try:
        return asyncio.run(_with_timeout())
    except asyncio.TimeoutError as exc:
        raise RuntimeError(
            f"Conversation timed out after {_CONVERSATION_TIMEOUT}s — "
            "the session may be stuck waiting for a webhook or ElevenLabs response"
        ) from exc
