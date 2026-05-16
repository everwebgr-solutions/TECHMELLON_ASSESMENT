"""
ElevenLabs Conversational AI — WebSocket client for text-mode sessions.

Connects to wss://api.elevenlabs.io/v1/convai/conversation and drives
turn-by-turn text exchange:
  - Client → Server: {"type": "user_message", "text": "..."}
  - Server → Client: {"type": "agent_response", "agent_response_event": {...}}

Ping events are answered immediately with pong. Audio events are discarded
(the agent generates TTS server-side but we never request or consume it).
The session is closed explicitly after each conversation to keep credit
usage proportional to actual conversation length.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from config import ELEVENLABS_API_KEY

logger = logging.getLogger(__name__)

_WS_BASE = "wss://api.elevenlabs.io/v1/convai/conversation"
# Agent tool calls (webhook round-trips) can take several seconds — be generous.
_RECV_TIMEOUT = 90.0


class ChatSession:
    """One text-mode conversation session with an ElevenLabs agent."""

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id
        self._ws = None
        self.conversation_id: Optional[str] = None

    async def connect(self) -> None:
        import websockets

        url = f"{_WS_BASE}?agent_id={self._agent_id}"
        self._ws = await websockets.connect(
            url,
            additional_headers={"xi-api-key": ELEVENLABS_API_KEY},
            open_timeout=30,
        )
        # The very first server frame is always conversation_initiation_metadata.
        raw = await asyncio.wait_for(self._ws.recv(), timeout=30.0)
        data = json.loads(raw)
        if data.get("type") == "conversation_initiation_metadata":
            self.conversation_id = (
                data.get("conversation_initiation_metadata_event", {})
                .get("conversation_id")
            )
        logger.debug("[WS] Session opened: %s", self.conversation_id)

    async def send(self, text: str) -> str:
        """
        Send a customer utterance and return the agent's text response.

        Handles ping/pong in-loop and silently discards audio, interruption,
        and internal_tentative_agent_response events.
        """
        await self._ws.send(json.dumps({
            "type": "user_message",
            "text": text,
        }))

        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=_RECV_TIMEOUT)
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "ping":
                event_id = msg.get("ping_event", {}).get("event_id")
                await self._ws.send(json.dumps({"type": "pong", "event_id": event_id}))

            elif msg_type == "agent_response":
                response = msg.get("agent_response_event", {}).get("agent_response", "")
                if response:
                    logger.debug("[WS] Agent: %.80s", response)
                    return response

            elif msg_type not in (
                "audio",
                "internal_tentative_agent_response",
                "interruption",
                "agent_response_correction",
            ):
                logger.debug("[WS] Unhandled event type: %s", msg_type)

    async def close(self) -> None:
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
            logger.debug("[WS] Session closed: %s", self.conversation_id)
