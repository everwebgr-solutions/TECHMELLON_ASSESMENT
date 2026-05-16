"""
Typed SSE event emitter.
The loop calls emit() which broadcasts to all connected UI clients.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List


class EventBus:
    def __init__(self):
        self._queues: List[asyncio.Queue] = []
        self._history: List[Dict[str, Any]] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._queues.discard(q) if hasattr(self._queues, "discard") else None
        try:
            self._queues.remove(q)
        except ValueError:
            pass

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Thread-safe emit — can be called from the loop thread."""
        event = {"type": event_type, **payload}
        self._history.append(event)

        for q in list(self._queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def emit_from_thread(self, event_type: str, payload: Dict[str, Any], loop: asyncio.AbstractEventLoop) -> None:
        """Emit from a non-async thread into an async event loop."""
        loop.call_soon_threadsafe(self.emit, event_type, payload)

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    def format_sse(self, event: Dict[str, Any]) -> str:
        return f"data: {json.dumps(event)}\n\n"


bus = EventBus()
