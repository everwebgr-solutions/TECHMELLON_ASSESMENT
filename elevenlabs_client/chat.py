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
  - Ping events are answered immediately with pong.
  - Audio events are discarded: the agent always generates TTS server-side
    but we never consume it (text-mode simulation).
  - Two-layer timeout: _MSG_TIMEOUT per individual WebSocket frame,
    _TURN_TIMEOUT as an absolute deadline for one full agent response.
    This prevents both slow-webhook hangs and silent connection drops.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from config import ELEVENLABS_API_KEY

logger = logging.getLogger(__name__)

_WS_BASE = "wss://api.elevenlabs.io/v1/convai/conversation"

# Maximum wait for a single WebSocket frame.  Keeps the loop responsive to
# connection drops without being too short for slow webhook round-trips.
_MSG_TIMEOUT = 30.0

# Hard ceiling for one complete agent turn (send → agent_response).
# Webhook calls can be slow; 120 s is generous without hanging forever.
_TURN_TIMEOUT = 120.0

_CONNECT_TIMEOUT = 30.0


class ChatSession:
    """One text-mode conversation session with an ElevenLabs agent."""

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id
        self._ws = None
        self.conversation_id: Optional[str] = None

    async def connect(self) -> None:
        import websockets

        url = f"{_WS_BASE}?agent_id={self._agent_id}"
        self._ws = await asyncio.wait_for(
            websockets.connect(
                url,
                additional_headers={"xi-api-key": ELEVENLABS_API_KEY},
                open_timeout=_CONNECT_TIMEOUT,
                # WebSocket-level keepalive: detects silent drops and sends
                # automatic pings every 20 s, failing after 10 s with no pong.
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

        # Required acknowledgment: tell the server we are ready and in text
        # mode.  Without this frame, newer API versions may silently ignore
        # subsequent user_message events.  optimize_streaming_latency=4 asks
        # ElevenLabs to minimise audio buffering (less server-side work per
        # audio frame, even though we discard those frames).
        await self._ws.send(json.dumps({
            "type": "conversation_initiation_client_data",
            "conversation_config_override": {
                "tts": {
                    "optimize_streaming_latency": 4,
                },
            },
        }))

    async def send(self, text: str) -> str:
        """
        Send a customer utterance and return the agent's text response.

        Uses a deadline (_TURN_TIMEOUT) so the call always terminates, plus
        a per-frame timeout (_MSG_TIMEOUT) to catch silent connection drops
        early rather than waiting for the full deadline.
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
                # Per-frame timeout expired but turn deadline has time left —
                # the connection is likely dead.
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
                if response.strip():
                    logger.debug("[WS] Agent: %.80s", response)
                    return response
                # Empty/whitespace response — wait for the substantive one.

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
