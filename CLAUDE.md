# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
make install          # pip install -r requirements.txt

# Database
make migrate          # Run Alembic migrations
make seed             # Seed 756 flights (7 days × 6 destinations × 3 classes)

# Run servers
make dev              # API server on http://localhost:8000 (uvicorn --reload)
make ui               # Observer UI on http://localhost:8001

# ElevenLabs setup (one-time)
make setup-agent      # Create agent, writes ELEVENLABS_AGENT_ID to .env

# Autonomous refinement loop
make loop             # python -m refinement.loop

# Tests
make test             # pytest tests/ -v --tb=short  (43 tests)
make test-cov         # With HTML coverage in htmlcov/

# Lint / syntax check
make lint             # Syntax-checks the 4 patchable files
make clean            # Remove __pycache__, *.pyc, reset database
```

## Architecture

The system is an **autonomous refinement loop** for a Sky Airways voice AI agent powered by ElevenLabs. It simulates customer conversations, evaluates them, then patches the agent's system prompt or the backend API code — iterating until all quality scores exceed a threshold or the iteration cap is reached.

### Modules

**`api/`** — FastAPI REST backend. Routes: flights, bookings, webhooks (ElevenLabs tool calls), knowledge. SQLAlchemy + SQLite. Seat availability is decremented inside a serializable transaction with a CHECK constraint to prevent double-booking. Alembic manages migrations (schema is Postgres-ready).

**`llm/`** — Provider abstraction. `llm/router.py::get_provider(task)` resolves which LLM to use for each task (`simulator`, `evaluator`, `prompt_fixer`, `code_patcher`) by reading `LLM_*` env vars. Supported backends: Ollama (default/local), OpenAI, Anthropic.

**`refinement/`** — The core loop (`loop.py` is the entry point):
1. **Simulator** (`simulator.py`) — LLM plays a customer using one of 10 scenarios; drives ElevenLabs Chat Mode API (text, no audio).
2. **Evaluator** (`evaluator.py`) — Scores transcripts on 4 criteria (1–10): `understanding`, `api_correctness`, `outcome_confirmation`, `naturalness`.
3. **Failure classification** — `prompt` failure → prompt fixer; `code` failure → code patcher.
4. **Prompt fixer** (`prompt_fixer.py`) — Rewrites system prompt and pushes to ElevenLabs.
5. **Code patcher** (`code_patcher.py`) — Generates targeted function-level patches with automatic rollback on failure. Safety gates: syntax check → AST scope check → full test suite. Only 4 files are patchable (`config.PATCHABLE_FILES`).
6. **State** (`state.py`) — Persists iteration history to `logs/run_{id}.json`.

**`knowledge_base/`** — Policy lookup via `GET /api/v1/knowledge/{topic}`. Deterministic JSON retrieval (no vector DB); topics: `pet_policy`, `baggage_allowance`, `special_assistance`, `check_in_windows`, `cancellation_refund`.

**`ui/`** — FastAPI + SSE observer dashboard (no build toolchain). `ui/events.py` is the event bus; `ui/server.py` serves static HTML and the `/events` SSE stream. Trigger the refinement loop via `POST /start`.

**`elevenlabs_client/`** — Thin wrappers: `agent.py` (create/update/push prompt), `chat.py` (Chat Mode session), `setup.py` (one-time agent creation).

### Data flow

```
refinement/loop.py
  → simulator.py  (LLM as customer)  →  ElevenLabs Chat Mode API
  → evaluator.py  (score transcript)
  → prompt_fixer / code_patcher
      code_patcher: generates patch → syntax check → AST check → run tests → apply or rollback
  → elevenlabs_client/agent.py  (push updated prompt)
  → state.py  (save to logs/)
```

### Key configuration (`config.py` + `.env`)

| Variable | Default | Purpose |
|---|---|---|
| `ELEVENLABS_API_KEY` | required | ElevenLabs auth |
| `ELEVENLABS_AGENT_ID` | set by `make setup-agent` | Agent to refine |
| `LLM_SIMULATOR` | `ollama/llama3.2` | Customer roleplay model |
| `LLM_EVALUATOR` | `ollama/llama3.2` | Scoring model |
| `LLM_PROMPT_FIXER` | `ollama/qwen2.5-coder` | Prompt rewrite model |
| `LLM_CODE_PATCHER` | `ollama/qwen2.5-coder` | Patch generation model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local LLM endpoint |
| `MAX_ITERATIONS` | `5` | Loop cap |
| `PASS_THRESHOLD` | `8.0` | Score to stop early |
| `MAX_CONVERSATION_TURNS` | `12` | Turns per simulation |
| `DATABASE_URL` | `sqlite:///./data/airline.db` | Booking DB |
| `PATCHABLE_FILES` | 4 files | Files the code patcher may modify |

Swap to a hosted LLM by setting e.g. `LLM_EVALUATOR=openai/gpt-4o` or `LLM_CODE_PATCHER=anthropic/claude-sonnet-4-6`.

### Tests

Five pytest files covering API routes, booking lifecycle, concurrent seat-constraint enforcement, webhook endpoints, and knowledge base lookup. Run a single file: `pytest tests/test_bookings.py -v`.

The code patcher's safety gate runs the full test suite before applying any patch — a patch that breaks tests is automatically rolled back.
