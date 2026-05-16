"""
Conversation simulator — an LLM plays a customer.

The simulator drives a conversation with the ElevenLabs agent via Chat Mode.
The customer LLM is given the scenario brief and instructed to pursue the goal
naturally but persistently, within MAX_CONVERSATION_TURNS.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from config import MAX_CONVERSATION_TURNS
from elevenlabs_client.chat import ConversationSession
from llm.base import LLMMessage, with_retry
from llm.router import get_provider
from refinement.scenarios import Scenario

_CUSTOMER_SYSTEM_PROMPT = """\
You are roleplaying as a customer calling an airline customer service line.
You have a specific goal. Pursue it naturally through conversation.

Rules:
- Stay in character as the customer at all times
- Respond naturally and briefly (1-3 sentences per turn)
- If the agent asks for information, provide it from your brief
- If your goal is achieved, say "That's perfect, thank you" and then say goodbye
- If the agent cannot help after 3 attempts, politely give up
- Do NOT play both sides of the conversation
- Do NOT describe actions in brackets like [hangs up]
- Output ONLY what the customer would say, nothing else
"""


def _build_customer_messages(
    scenario: Scenario,
    conversation_so_far: List[Dict[str, str]],
    latest_agent_message: str,
) -> List[Dict[str, str]]:
    history_text = ""
    for turn in conversation_so_far:
        role = "Agent" if turn["role"] == "agent" else "You (customer)"
        history_text += f"{role}: {turn['content']}\n"

    user_content = (
        f"Your goal: {scenario['customer_brief']}\n\n"
        f"Conversation so far:\n{history_text}\n"
        f"Agent just said: {latest_agent_message}\n\n"
        f"What do you say next? (respond as the customer only)"
    )

    return [
        LLMMessage.system(_CUSTOMER_SYSTEM_PROMPT),
        LLMMessage.user(user_content),
    ]


def simulate_conversation(
    agent_id: str,
    scenario: Scenario,
    on_turn: Optional[callable] = None,
) -> List[Dict[str, str]]:
    """
    Run a full simulated conversation for a given scenario.

    Args:
        agent_id: ElevenLabs agent ID
        scenario: The customer scenario to simulate
        on_turn: Optional callback(role, content) called after each turn for real-time streaming

    Returns:
        Full transcript as list of {role, content, timestamp} dicts
    """
    customer_llm = get_provider("simulator")
    session = ConversationSession(agent_id)

    try:
        session.start()

        # Get the agent's opening greeting
        if session.transcript:
            greeting = session.transcript[-1]["content"]
        else:
            greeting = "Thank you for calling Sky Airways. How can I help you?"

        if on_turn:
            on_turn("agent", greeting)

        for turn_num in range(MAX_CONVERSATION_TURNS):
            # Customer LLM generates the next customer message
            messages = _build_customer_messages(scenario, session.transcript, greeting)

            try:
                customer_message = with_retry(
                    customer_llm.complete,
                    messages,
                    max_attempts=3,
                    temperature=0.8,
                )
            except Exception as exc:
                customer_message = f"I'm sorry, I'm having trouble. Could you help me?"

            if on_turn:
                on_turn("user", customer_message)

            # Send to ElevenLabs agent
            try:
                agent_response = session.send(customer_message)
            except Exception as exc:
                agent_response = f"[Error: agent did not respond — {exc}]"
                session.transcript.append(
                    {"role": "agent", "content": agent_response, "timestamp": _ts()}
                )
                break

            if on_turn:
                on_turn("agent", agent_response)

            greeting = agent_response  # next iteration uses this as context

            # Detect natural conversation end
            farewell_signals = [
                "goodbye", "bye", "have a great", "is there anything else",
                "thank you for calling", "have a safe", "safe travels"
            ]
            customer_farewell = any(w in customer_message.lower() for w in ["goodbye", "bye", "thank you, goodbye", "that's all"])
            if customer_farewell and turn_num >= 1:
                break

    finally:
        session.end()

    return session.transcript


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
