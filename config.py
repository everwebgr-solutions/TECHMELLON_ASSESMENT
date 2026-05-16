"""
Central configuration — all values read from environment with safe defaults.
Import this module everywhere; never read os.environ directly in business logic.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Project paths ─────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = ROOT_DIR / "logs"
PATCHES_BACKUP_DIR = DATA_DIR / "patches" / "backup"

for _d in (DATA_DIR, LOGS_DIR, PATCHES_BACKUP_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Tunnel ────────────────────────────────────────────────────────────────────
# Optional ngrok auth token — required for stable tunnels (free account at ngrok.com).
# Without it pyngrok still works but is limited to one session and may be slower.
NGROK_AUTHTOKEN: str = os.environ.get("NGROK_AUTHTOKEN", "")

# ── ElevenLabs ────────────────────────────────────────────────────────────────
ELEVENLABS_API_KEY: str = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_AGENT_ID: str = os.environ.get("ELEVENLABS_AGENT_ID", "")
ELEVENLABS_VOICE_ID: str = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
ELEVENLABS_BASE_URL: str = "https://api.elevenlabs.io/v1"

# ── LLM providers ─────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")

# Task → "provider/model" routing
LLM_SIMULATOR: str = os.environ.get("LLM_SIMULATOR", "ollama/llama3.2")
LLM_EVALUATOR: str = os.environ.get("LLM_EVALUATOR", "ollama/llama3.2")
LLM_PROMPT_FIXER: str = os.environ.get("LLM_PROMPT_FIXER", "ollama/qwen2.5-coder")
LLM_CODE_PATCHER: str = os.environ.get("LLM_CODE_PATCHER", "ollama/qwen2.5-coder")

# ── Refinement loop ───────────────────────────────────────────────────────────
MAX_ITERATIONS: int = int(os.environ.get("MAX_ITERATIONS", "5"))
PASS_THRESHOLD: float = float(os.environ.get("PASS_THRESHOLD", "8.0"))
MAX_CONVERSATION_TURNS: int = int(os.environ.get("MAX_CONVERSATION_TURNS", "12"))

# ── API server ────────────────────────────────────────────────────────────────
API_HOST: str = os.environ.get("API_HOST", "0.0.0.0")
API_PORT: int = int(os.environ.get("API_PORT", "8000"))
UI_PORT: int = int(os.environ.get("UI_PORT", "8001"))
API_BASE_URL: str = f"http://localhost:{API_PORT}"

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR}/airline.db")

# ── Patchable files (code patcher scope — do not expand without review) ───────
PATCHABLE_FILES: list[str] = [
    "api/routes/webhooks.py",
    "api/services/booking_service.py",
    "api/services/flight_service.py",
    "knowledge_base/kb_service.py",
]
