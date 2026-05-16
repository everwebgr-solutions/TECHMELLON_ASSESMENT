"""
ElevenLabs Chat Mode (text-based conversation) client.

Uses the /convai/conversations endpoint to drive a conversation
programmatically — no audio required.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx

from config import ELEVENLABS_API_KEY, ELEVENLABS_BASE_URL

_HEADERS = {
    "xi-api-key": ELEVENLABS_API_KEY,
    "Content-Type": "application/json",
}


class ConversationSession:
    """
    Manages a single ElevenLabs text-mode conversation session.

    Usage:
        session = ConversationSession(agent_id)
        session.start()
        reply = session.send("I want to book a flight to Paris")
        session.end()
        transcript = session.transcript
    """

    def __init__(self, agent_id: str):
        self._agent_id = agent_id
        self._conversation_id: Optional[str] = None
        self.transcript: List[Dict[str, str]] = []

    def start(self) -> str:
        """Initiate a new conversation and return the conversation_id."""
        resp = httpx.post(
            f"{ELEVENLABS_BASE_URL}/convai/conversations",
            headers=_HEADERS,
            json={"agent_id": self._agent_id},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        self._conversation_id = data["conversation_id"]

        # Capture the agent's first message if present
        if "agent_response" in data and data["agent_response"]:
            self.transcript.append(
                {"role": "agent", "content": data["agent_response"], "timestamp": _ts()}
            )

        return self._conversation_id

    def send(self, user_message: str, timeout: float = 60.0) -> str:
        """
        Send a user message and return the agent's text response.
        Polls if the response is not immediately available.
        """
        if not self._conversation_id:
            raise RuntimeError("Session not started. Call start() first.")

        self.transcript.append(
            {"role": "user", "content": user_message, "timestamp": _ts()}
        )

        resp = httpx.post(
            f"{ELEVENLABS_BASE_URL}/convai/conversations/{self._conversation_id}/message",
            headers=_HEADERS,
            json={"text": user_message},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        agent_response = data.get("agent_response") or data.get("response", "")

        # If no immediate response, poll for it
        if not agent_response:
            agent_response = self._poll_response(timeout=timeout)

        self.transcript.append(
            {"role": "agent", "content": agent_response, "timestamp": _ts()}
        )
        return agent_response

    def _poll_response(self, timeout: float = 60.0) -> str:
        """Poll conversation status until agent response is available."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = httpx.get(
                f"{ELEVENLABS_BASE_URL}/convai/conversations/{self._conversation_id}",
                headers=_HEADERS,
                timeout=15.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                messages = data.get("transcript", [])
                # Find the latest agent message not yet in our transcript
                for msg in reversed(messages):
                    if msg.get("role") == "agent":
                        content = msg.get("message", "")
                        if content:
                            return content
            time.sleep(2.0)
        return "[No response received within timeout]"

    def end(self) -> None:
        """Close the conversation session."""
        if self._conversation_id:
            try:
                httpx.delete(
                    f"{ELEVENLABS_BASE_URL}/convai/conversations/{self._conversation_id}",
                    headers=_HEADERS,
                    timeout=10.0,
                )
            except Exception:
                pass  # Best-effort close

    def get_full_transcript(self) -> List[Dict[str, str]]:
        """
        Fetch the authoritative transcript from ElevenLabs.
        Useful to capture tool calls and intermediate steps.
        """
        if not self._conversation_id:
            return self.transcript
        try:
            resp = httpx.get(
                f"{ELEVENLABS_BASE_URL}/convai/conversations/{self._conversation_id}",
                headers=_HEADERS,
                timeout=15.0,
            )
            if resp.status_code == 200:
                raw = resp.json().get("transcript", [])
                return [
                    {
                        "role": m.get("role", "unknown"),
                        "content": m.get("message", ""),
                        "timestamp": m.get("time_in_call_secs", 0),
                    }
                    for m in raw
                ]
        except Exception:
            pass
        return self.transcript


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
