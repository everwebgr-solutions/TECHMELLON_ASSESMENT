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

# Frontend (rebuild after UI changes)
cd ui/frontend && npm run build   # outputs to ui/static/
```

## Architecture

The system is an **autonomous refinement loop** for a Sky Airways voice AI agent powered by ElevenLabs. It simulates customer conversations, evaluates them, then patches the agent's system prompt or the backend API code — iterating until all quality scores exceed a threshold or the iteration cap is reached.

### Modules

**`api/`** — FastAPI REST backend (port 8000). Routes: flights, bookings, webhooks (ElevenLabs tool calls), knowledge. SQLAlchemy + SQLite. Seat availability is decremented inside a serializable transaction with a CHECK constraint to prevent double-booking. Alembic manages migrations (schema is Postgres-ready).

Webhook routes also expose two cross-process endpoints used by the refinement loop:
- `GET /api/v1/webhooks/tool-calls` — returns the in-memory log of tool calls made during the last simulation
- `DELETE /api/v1/webhooks/tool-calls` — clears the log before a new simulation starts

Every webhook handler calls `_log_call(tool, inputs, result)` to record what was called, with what parameters, and whether it succeeded.

**`llm/`** — Provider abstraction. `llm/router.py::get_provider(task)` resolves which LLM to use for each task (`simulator`, `evaluator`, `prompt_fixer`, `code_patcher`) by reading `LLM_*` env vars. Supported backends: Ollama (default/local), OpenAI, Anthropic. `llm/base.py::with_retry` retries on failure and injects parse error feedback into the message list on structured output failures.

**`refinement/`** — The core loop (`loop.py` is the entry point):
1. **Scenario selection** — One scenario is chosen for the entire run. The index is persisted to `data/scenario_state.json` so each new run advances to the next scenario in the 15-scenario rotation. A specific scenario can be pinned by passing `scenario_id` to `run_loop()`.
2. **Simulator** (`simulator.py`) — LLM plays a customer; drives ElevenLabs Chat Mode WebSocket (text input, audio discarded). Sends `conversation_initiation_client_data` after connect. Two-layer timeout: 30s per WebSocket frame, 120s absolute deadline per agent turn. 5-minute overall conversation timeout.
3. **Evaluator** (`evaluator.py`) — Scores transcripts on 4 criteria (1–10): `understanding`, `api_correctness`, `outcome_confirmation`, `naturalness`. The loop fetches the tool call log from the API server over HTTP and passes it to the evaluator as ground truth for `api_correctness` and root cause classification.
4. **Regression check** — If the new average score is lower than the previous iteration's, all fixes from that iteration are rolled back: prompt restored to checkpoint, code patches reversed from backup. The loop then continues without applying new fixes.
5. **Failure classification** — `prompt` failure → prompt fixer; `code` failure → code patcher.
6. **Prompt fixer** (`prompt_fixer.py`) — Rewrites system prompt targeting specific failures and pushes to ElevenLabs via PATCH (date header is always re-injected; date prefix from previous runs is stripped on fetch to prevent accumulation).
7. **Code patcher** (`code_patcher.py`) — Generates targeted function-level patches. Safety gates: syntax check → AST scope check → full test suite. Two rollback triggers: test failure or evaluation regression. Only files in `config.PATCHABLE_FILES` are patchable.
8. **State** (`state.py`) — Persists iteration history to `logs/run_{id}.json`. Each iteration record includes `rolled_back: bool`.

**`knowledge_base/`** — Policy lookup via `GET /api/v1/knowledge/{topic}`. Deterministic JSON retrieval (no vector DB); topics: `pet_policy`, `baggage_allowance`, `special_assistance`, `check_in_windows`, `cancellation_refund_policy`.

**`ui/`** — FastAPI (port 8001) + SSE observer dashboard. React/Vite frontend (`ui/frontend/`) built to `ui/static/`. `ui/events.py` is the event bus; `ui/server.py` serves the built assets and the `/events` SSE stream. Key UI server endpoints:
- `POST /start` — accepts optional `{"scenario_id": "..."}` body; triggers loop in a background thread
- `GET /scenarios` — returns the list of all 15 scenarios for the UI dropdown
- `POST /reset` — force-resets loop state

**`elevenlabs_client/`** — `agent.py`: `update_agent_tools(agent_id, base_url)` PATCHes webhook URLs on the existing agent; `update_agent_prompt(agent_id, prompt)` PATCHes the prompt. A new agent is never created by the loop — only by `make setup-agent`. `chat.py`: WebSocket driver with `ping_interval=20`, two-layer timeout, `ConnectionClosed` handling, and mandatory `conversation_initiation_client_data` acknowledgment.

### Data flow

```
refinement/loop.py
  → DELETE http://localhost:8000/api/v1/webhooks/tool-calls  (clear log)
  → simulator.py  (LLM as customer)
      → ElevenLabs Chat Mode WebSocket (text in, text out, audio discarded)
          → ElevenLabs calls our webhooks → api/routes/webhooks.py logs each call
  → GET http://localhost:8000/api/v1/webhooks/tool-calls  (fetch log)
  → evaluator.py  (score transcript + tool call evidence)
  → regression check → rollback if score worsened
  → prompt_fixer / code_patcher
      code_patcher: generates patch → syntax check → AST check → run tests → apply or rollback
  → elevenlabs_client/agent.py  (PATCH prompt on existing agent)
  → state.py  (save to logs/)
```

### Key configuration (`config.py` + `.env`)

| Variable | Default | Purpose |
|---|---|---|
| `ELEVENLABS_API_KEY` | required | ElevenLabs auth |
| `ELEVENLABS_AGENT_ID` | set by `make setup-agent` | Agent updated in-place each run |
| `NGROK_AUTHTOKEN` | required | Public tunnel for ElevenLabs webhook delivery |
| `LLM_SIMULATOR` | `ollama/llama3.2` | Customer roleplay model |
| `LLM_EVALUATOR` | `ollama/llama3.2` | Scoring model |
| `LLM_PROMPT_FIXER` | `ollama/qwen2.5-coder` | Prompt rewrite model |
| `LLM_CODE_PATCHER` | `ollama/qwen2.5-coder` | Patch generation model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local LLM endpoint |
| `MAX_ITERATIONS` | `5` | Loop cap per run |
| `PASS_THRESHOLD` | `8.0` | Score to stop early |
| `MAX_CONVERSATION_TURNS` | `12` | Turns per simulation |
| `DATABASE_URL` | `sqlite:///./data/airline.db` | Booking DB |
| `PATCHABLE_FILES` | 4 files | Files the code patcher may modify |

Swap to a hosted LLM by setting e.g. `LLM_EVALUATOR=openai/gpt-4o` or `LLM_CODE_PATCHER=anthropic/claude-sonnet-4-6`.

### Scenarios

15 scenarios in `refinement/scenarios.py`. The rotation index is stored in `data/scenario_state.json`. Adding scenarios: append to the `SCENARIOS` list — the modulo rotation handles any length automatically.

### Tests

Five pytest files covering API routes, booking lifecycle, concurrent seat-constraint enforcement, webhook endpoints, and knowledge base lookup. Run a single file: `pytest tests/test_bookings.py -v`.

The code patcher's safety gate runs the full test suite before applying any patch — a patch that breaks tests is automatically rolled back.

### Important cross-process note

The API server (port 8000) and refinement loop run in **separate processes**. Any state that needs to cross this boundary must go through HTTP. The tool call log is the primary example: `api/routes/webhooks.py` holds it in memory; the loop reads it via `GET /api/v1/webhooks/tool-calls`. Do not attempt to import `api` modules directly from `refinement/` code for shared state.
