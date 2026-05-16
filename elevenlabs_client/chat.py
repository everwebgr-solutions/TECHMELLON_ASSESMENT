"""
ElevenLabs Conversational AI — WebSocket client for text-mode sessions.

Connects to wss://api.elevenlabs.io/v1/convai/conversation and drives
turn-by-turn text exchange:
  - Client → Server: {"type": "user_message", "text": "..."}
  - Server → Client: {"type": "agent_response", "agent_response_event": {...}}

Protocol notes:
  - After receiving conversation_initiation_metadata, a
    conversation_initiation_client_data acknowledgment MUST be sent before
    any user_message — some API versions will not respond without it.
  - After the ack, ElevenLabs sends an automatic opening greeting which must
    be drained before the first customer message is sent, otherwise the
    greeting occupies the buffer and gets returned as the "response" to turn 1.
  - Ping events are answered immediately with pong.
  - Audio events are discarded: the agent always generates TTS server-side
    but we never consume it (text-mode simulation).
  - Two-layer timeout: _MSG_TIMEOUT per individual WebSocket frame,
    _TURN_TIMEOUT as an absolute deadline for one full agent response.
    This prevents both slow-webhook hangs and silent connection drops.
  - Tentative filler responses ("...") are skipped — the agent emits these
    while processing webhook calls; only substantive text is returned.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from config import ELEVENLABS_API_KEY

logger = logging.getLogger(__name__)

_WS_BASE = "wss://api.elevenlabs.io/v1/convai/conversation"

# Maximum wait for a single WebSocket frame.
_MSG_TIMEOUT = 30.0

# Hard ceiling for one complete agent turn (send → agent_response).
_TURN_TIMEOUT = 120.0

_CONNECT_TIMEOUT = 30.0

# Responses that are pure filler while the agent is thinking / calling a webhook.
# Returning these as real turns confuses the simulator customer LLM.
_FILLER_RESPONSES = {"...", "…", ". . .", "...."}


def _is_filler(text: str) -> bool:
    stripped = text.strip()
    return stripped in _FILLER_RESPONSES or set(stripped).issubset({".", " ", "…"})


class ChatSession:
    """One text-mode conversation session with an ElevenLabs agent."""

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id
        self._ws = None
        self.conversation_id: Optional[str] = None
        self.opening_greeting: str = ""

    async def connect(self) -> None:
        import websockets

        url = f"{_WS_BASE}?agent_id={self._agent_id}"
        self._ws = await asyncio.wait_for(
            websockets.connect(
                url,
                additional_headers={"xi-api-key": ELEVENLABS_API_KEY},
                open_timeout=_CONNECT_TIMEOUT,
                ping_interval=20,
                ping_timeout=10,
            ),
            timeout=_CONNECT_TIMEOUT,
        )

        # First server frame is always conversation_initiation_metadata.
        raw = await asyncio.wait_for(self._ws.recv(), timeout=_CONNECT_TIMEOUT)
        data = json.loads(raw)
        if data.get("type") == "conversation_initiation_metadata":
            self.conversation_id = (
                data.get("conversation_initiation_metadata_event", {})
                .get("conversation_id")
            )
        logger.debug("[WS] Session opened: %s", self.conversation_id)

        await self._ws.send(json.dumps({
            "type": "conversation_initiation_client_data",
            "conversation_config_override": {
                "tts": {"optimize_streaming_latency": 4},
                "conversation": {"text_only": True},
            },
        }))

        # Drain the agent's automatic opening greeting.
        # ElevenLabs agents send an agent_response immediately after the ack.
        # If we don't consume it here it sits in the buffer and gets returned
        # as the "response" to the customer's first message, making the agent
        # appear to ignore everything the customer said.
        self.opening_greeting = await self._drain_greeting()
        logger.debug("[WS] Opening greeting: %.80s", self.opening_greeting)

    async def _drain_greeting(self) -> str:
        """
        Read frames until the first real agent_response or a short timeout.
        Returns the greeting text, or "" if none arrives within the window.
        """
        import websockets.exceptions
        try:
            deadline = asyncio.get_event_loop().time() + 15.0
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    return ""
                raw = await asyncio.wait_for(self._ws.recv(), timeout=min(8.0, remaining))
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    event_id = msg.get("ping_event", {}).get("event_id")
                    await self._ws.send(json.dumps({"type": "pong", "event_id": event_id}))

                elif msg_type == "agent_response":
                    text = msg.get("agent_response_event", {}).get("agent_response", "")
                    if text.strip() and not _is_filler(text):
                        return text

                elif msg_type == "error":
                    raise RuntimeError(f"ElevenLabs agent error during greeting: {msg}")

        except asyncio.TimeoutError:
            return ""
        except Exception:
            return ""

    async def send(self, text: str) -> str:
        """
        Send a customer utterance and return the agent's text response.

        Filler responses ("...") are skipped — the agent emits these while
        processing webhook calls; we wait for a substantive reply.
        """
        import websockets.exceptions

        await self._ws.send(json.dumps({
            "type": "user_message",
            "text": text,
        }))

        loop = asyncio.get_event_loop()
        deadline = loop.time() + _TURN_TIMEOUT

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(
                    f"Agent did not complete its response within {_TURN_TIMEOUT}s"
                )

            try:
                raw = await asyncio.wait_for(
                    self._ws.recv(),
                    timeout=min(_MSG_TIMEOUT, remaining),
                )
            except asyncio.TimeoutError:
                remaining_after = deadline - loop.time()
                if remaining_after <= 0:
                    raise TimeoutError(
                        f"Agent did not complete its response within {_TURN_TIMEOUT}s"
                    )
                raise TimeoutError(
                    f"No WebSocket frame received for {_MSG_TIMEOUT}s — "
                    "connection may be dead or webhook is unresponsive"
                )
            except websockets.exceptions.ConnectionClosed as exc:
                raise RuntimeError(
                    f"WebSocket closed unexpectedly (code={exc.code}): {exc.reason}"
                ) from exc

            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "ping":
                event_id = msg.get("ping_event", {}).get("event_id")
                await self._ws.send(json.dumps({"type": "pong", "event_id": event_id}))

            elif msg_type == "agent_response":
                response = msg.get("agent_response_event", {}).get("agent_response", "")
                if response.strip() and not _is_filler(response):
                    logger.debug("[WS] Agent: %.80s", response)
                    return response
                # Filler or empty — keep waiting for the substantive response.
                if response.strip():
                    logger.debug("[WS] Skipping filler response: %r", response)

            elif msg_type == "error":
                error_detail = msg.get("error", msg)
                raise RuntimeError(f"ElevenLabs agent error: {error_detail}")

            elif msg_type not in (
                "audio",
                "internal_tentative_agent_response",
                "interruption",
                "agent_response_correction",
                "conversation_initiation_client_data",
            ):
                logger.debug("[WS] Unhandled event type: %s", msg_type)

    async def close(self) -> None:
        if self._ws:
            try:
                await asyncio.wait_for(self._ws.close(), timeout=5.0)
            except Exception:
                pass
            self._ws = None
            logger.debug("[WS] Session closed: %s", self.conversation_id)
