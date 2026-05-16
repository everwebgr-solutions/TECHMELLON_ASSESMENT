"""
UI server — FastAPI + SSE for real-time loop observation.

Endpoints:
  GET /          → dashboard HTML
  GET /events    → SSE stream of all loop events
  GET /history   → JSON of all events so far (for page reload)
  POST /start    → trigger the refinement loop in a background thread
  GET /status    → current loop status
"""
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import ELEVENLABS_AGENT_ID, LOGS_DIR
from ui.events import bus

app = FastAPI(title="Sky Airways Refinement Loop — Observer UI")

_STATIC_DIR = Path(__file__).parent / "static"

# Loop state
_loop_running = False
_loop_thread: Optional[threading.Thread] = None
_main_event_loop: Optional[asyncio.AbstractEventLoop] = None


@app.on_event("startup")
async def _store_event_loop():
    global _main_event_loop
    _main_event_loop = asyncio.get_event_loop()


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = _STATIC_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse("<h1>UI files not found</h1>")


@app.get("/events")
async def sse_stream():
    """Server-Sent Events stream for real-time loop updates."""
    async def generate() -> AsyncGenerator[str, None]:
        # Send history first so a fresh page load catches up
        for event in bus.get_history():
            yield bus.format_sse(event)

        q = bus.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield bus.format_sse(event)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"  # keep connection alive
        except asyncio.CancelledError:
            bus.unsubscribe(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/history")
async def history():
    return JSONResponse({"events": bus.get_history()})


@app.get("/status")
async def status():
    return JSONResponse({
        "loop_running": _loop_running,
        "agent_id": ELEVENLABS_AGENT_ID,
        "event_count": len(bus.get_history()),
    })


@app.post("/start")
async def start_loop():
    """Trigger the refinement loop in a background thread."""
    global _loop_running, _loop_thread

    if _loop_running:
        return JSONResponse({"error": "Loop is already running"}, status_code=409)

    if not ELEVENLABS_AGENT_ID:
        return JSONResponse(
            {"error": "ELEVENLABS_AGENT_ID not configured. Run 'make setup-agent' first."},
            status_code=400,
        )

    _loop_running = True

    def run_in_thread():
        global _loop_running
        try:
            from refinement.loop import run_loop

            def on_event(event_type: str, payload: dict):
                if _main_event_loop:
                    bus.emit_from_thread(event_type, payload, _main_event_loop)

            run_loop(on_event=on_event)
        except Exception as exc:
            if _main_event_loop:
                bus.emit_from_thread("error", {"message": str(exc)}, _main_event_loop)
        finally:
            _loop_running = False

    _loop_thread = threading.Thread(target=run_in_thread, daemon=True)
    _loop_thread.start()

    return JSONResponse({"message": "Loop started", "agent_id": ELEVENLABS_AGENT_ID})


@app.get("/logs")
async def list_logs():
    """List available run log files."""
    logs = sorted(LOGS_DIR.glob("run_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return JSONResponse({"logs": [p.name for p in logs[:10]]})


@app.get("/logs/{filename}")
async def get_log(filename: str):
    """Fetch a specific run log."""
    log_path = LOGS_DIR / filename
    if not log_path.exists() or not log_path.name.startswith("run_"):
        return JSONResponse({"error": "Log not found"}, status_code=404)
    return JSONResponse(json.loads(log_path.read_text()))
