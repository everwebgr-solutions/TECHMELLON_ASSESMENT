"""
Typed SSE event emitter with file-backed history.

History is written to logs/current_run.jsonl so that a server restart
(e.g. from uvicorn --reload) does not lose the current loop's events.
On a new loop_started event the file is cleared so stale data never bleeds
into a fresh run.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

from config import LOGS_DIR

_HISTORY_FILE = LOGS_DIR / "current_run.jsonl"


def _load_history() -> List[Dict[str, Any]]:
    if not _HISTORY_FILE.exists():
        return []
    events: List[Dict[str, Any]] = []
    for line in _HISTORY_FILE.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


class EventBus:
    def __init__(self):
        self._queues: List[asyncio.Queue] = []
        self._history: List[Dict[str, Any]] = _load_history()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._queues.remove(q)
        except ValueError:
            pass

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Thread-safe emit — can be called from the loop thread."""
        # Clear history file on a new loop so stale events never replay
        if event_type == "loop_started":
            self._history.clear()
            try:
                _HISTORY_FILE.write_text("")
            except OSError:
                pass

        event = {"type": event_type, **payload}
        self._history.append(event)

        # Persist to disk
        try:
            with _HISTORY_FILE.open("a") as f:
                f.write(json.dumps(event) + "\n")
        except OSError:
            pass

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
