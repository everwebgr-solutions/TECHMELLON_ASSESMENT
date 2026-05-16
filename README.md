# Sky Airways — Voice AI Agent with Autonomous Refinement Loop

A production-grade MVP of an ElevenLabs-powered airline voice AI agent with a fully autonomous self-correcting pipeline.

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in: ELEVENLABS_API_KEY, NGROK_AUTHTOKEN
# Optional: OPENAI_API_KEY or ANTHROPIC_API_KEY for hosted LLM providers
# Ollama is the default LLM provider — no API key needed for local runs
```

### 3. Start Ollama (local LLM, default)

```bash
ollama serve
ollama pull llama3.2
ollama pull qwen2.5-coder
```

### 4. Set up the database

```bash
make migrate     # run Alembic migrations
make seed        # seed 756 flights across 7 days
```

### 5. Start both servers

```bash
make start       # builds the UI, then starts API (port 8000) + observer UI (port 8001) together
                 # Ctrl-C stops both
```

Or run them separately:

```bash
make dev         # API server only — http://localhost:8000
make ui          # Observer UI only — http://localhost:8001
```

To kill both servers when running in the background:

```bash
make stop        # kills any process on ports 8000 and 8001
```

### 6. Create the ElevenLabs agent (one-time)

```bash
make setup-agent
# Writes ELEVENLABS_AGENT_ID to .env
```

### 7. Run the refinement loop

```bash
make loop        # runs autonomously, prints progress to stdout
```

### 8. Watch it in real time

Open `http://localhost:8001` → select a scenario or leave on Auto → click **Start Loop**.

---

## Architecture

```
airline-voice-agent/
├── api/                    FastAPI backend — flights, bookings, webhooks
│   ├── models/             SQLAlchemy ORM models (Flight, Booking)
│   ├── schemas/            Pydantic request/response schemas
│   ├── routes/             HTTP route handlers (webhooks, flights, bookings, knowledge)
│   └── services/           Business logic (flight_service, booking_service)
├── knowledge_base/         JSON policy store + lookup service
├── llm/                    Provider abstraction (Ollama, OpenAI, Anthropic)
├── elevenlabs_client/      Agent management + Chat Mode WebSocket driver
├── refinement/             The autonomous loop
│   ├── loop.py             Orchestrator
│   ├── simulator.py        LLM-as-customer conversation driver
│   ├── evaluator.py        Structured transcript scoring with tool call evidence
│   ├── prompt_fixer.py     Prompt rewriter
│   ├── code_patcher.py     Targeted function-level patching with rollback
│   ├── state.py            Iteration state + JSON log persistence
│   └── scenarios.py        15 customer scenarios
├── ui/                     FastAPI + SSE observer dashboard (React/Vite frontend)
└── tests/                  43 pytest tests
```

---

## APIs and Tools Used

| Tool | Purpose |
|------|---------|
| **ElevenLabs** | Voice agent runtime + Chat Mode WebSocket API for text-based simulation |
| **FastAPI** | REST API + webhooks + SSE UI server |
| **SQLAlchemy + SQLite** | Booking database with WAL mode and seat constraint enforcement |
| **Alembic** | Schema migrations |
| **Ollama** | Local LLM provider (llama3.2, qwen2.5-coder) — default, no cost |
| **OpenAI / Anthropic** | Optional hosted providers for higher evaluation quality |
| **Pydantic v2** | Structured output schemas for evaluator and all API models |
| **pyngrok** | Exposes the local API server publicly so ElevenLabs can reach webhook endpoints |
| **pytest** | 43 tests covering API, consistency, webhooks, knowledge base |

---

## LLM Provider Strategy

The system uses a provider abstraction layer. Each task routes to a configurable model:

```
LLM_SIMULATOR=ollama/llama3.2        # customer roleplay
LLM_EVALUATOR=ollama/llama3.2        # transcript scoring
LLM_PROMPT_FIXER=ollama/qwen2.5-coder
LLM_CODE_PATCHER=ollama/qwen2.5-coder
```

**Default: Ollama (local, free).** Swap any task to OpenAI or Anthropic by changing one line in `.env`:

```bash
LLM_EVALUATOR=openai/gpt-4o                       # higher consistency on structured scoring
LLM_CODE_PATCHER=anthropic/claude-sonnet-4-6      # stronger code reasoning
```

---

## Refinement Loop Design

### Scenario selection

The loop picks **one scenario for the entire run** and optimises against it across all iterations. The scenario index is persisted to `data/scenario_state.json` so each new run automatically advances to the next scenario in the 15-scenario rotation. You can also manually pin a scenario from the UI dropdown.

### Cycle (per iteration)

1. **Simulate** — An LLM plays a customer with the chosen scenario. Drives the ElevenLabs agent via Chat Mode WebSocket (text mode, audio discarded). Up to `MAX_CONVERSATION_TURNS` turns.
2. **Evaluate** — A separate LLM call scores the transcript on 4 criteria (1–10 each). The evaluator receives the actual tool call log (fetched from the API server over HTTP) so it can judge `api_correctness` from real evidence rather than inference from conversation text.
3. **Regression check** — If the new score is lower than the previous iteration's score, all fixes from the previous iteration are rolled back (prompt restored, code patches reversed from backup) and the loop retries without applying new fixes.
4. **Fix** — If prompt failures: LLM rewrites system prompt targeting the specific failures. If code failures: LLM generates a targeted patch for the identified function.
5. **Push** — Updated prompt sent to ElevenLabs via PATCH (the existing agent is updated in place; a new agent is never created mid-loop).
6. **Repeat** — Until all scores ≥ `PASS_THRESHOLD` or `MAX_ITERATIONS` reached.

### Termination

```python
MAX_ITERATIONS = 5      # configurable via .env
PASS_THRESHOLD = 8.0    # configurable via .env
```

### Code Patching Safety

Code patching is intentionally constrained:
- **Scope**: Only 4 files are patchable (defined in `config.PATCHABLE_FILES`)
- **Granularity**: Patches replace exactly one named function
- **Gates before apply**: syntax check → AST scope check → full test suite
- **Two rollback triggers**:
  - Test suite fails after patch → auto-restore from backup
  - Next iteration's evaluation score is worse → restore prompt + all code patches from that iteration

---

## Supported Agent Scenarios

The agent is tested against 15 customer scenarios across three difficulty levels:

| # | Scenario | Type |
|---|----------|------|
| 1 | Book the next available flight to a destination | Booking |
| 2 | Find and book cheapest ticket within the following week | Booking |
| 3 | Enquire about pet policy (cabin/hold rules, fees, notice) | Inquiry |
| 4 | Reschedule an existing booking to a different date | Modification |
| 5 | Enquire about baggage allowance (limits, excess fees) | Inquiry |
| 6 | Request cancellation and enquire about refund policy | Modification |
| 7 | Book a flight with a specific seat preference | Booking |
| 8 | Add an extra bag or special item to an existing booking | Modification |
| 9 | Enquire about check-in times, gate closure, flight status | Inquiry |
| 10 | Request wheelchair or special assistance | Inquiry |
| 11 | Claim EU261 compensation for a significantly delayed flight | Inquiry (harder) |
| 12 | Book a same-day flight with check-in deadline awareness | Booking (harder) |
| 13 | Book a flight and arrange cabin pet transport in one call | Booking (harder) |
| 14 | Enquire about upgrading an existing economy booking | Modification (harder) |

---

## Evaluation Criteria

Each conversation is scored on four criteria:

| Criterion | What it measures |
|-----------|-----------------|
| `understanding` | Was the customer's request correctly understood? |
| `api_correctness` | Was the right tool called with correct parameters? Did it succeed? |
| `outcome_confirmation` | Was the outcome clearly confirmed to the customer? |
| `naturalness` | Was the call handled naturally end-to-end? |

The evaluator classifies each failure's root cause:
- **`prompt`** — agent misunderstood, skipped a step, or was poorly instructed. Fixed by the prompt fixer.
- **`code`** — a webhook returned an error or wrong data. Fixed by the code patcher.

Root cause is determined from both the conversation transcript **and** the actual tool call log (tool name, inputs, success/error) captured from the API server during simulation.

---

## Webhook Tool Call Log

Every webhook invocation during a simulation is logged in the API server process:

```
GET  /api/v1/webhooks/tool-calls    — fetch the log (used by evaluator)
DELETE /api/v1/webhooks/tool-calls  — clear before next simulation
```

The loop clears the log before each simulation and retrieves it over HTTP after, passing it to the evaluator as ground truth for `api_correctness` scoring.

---

## Agent Webhook Tools

The ElevenLabs agent has access to 8 webhook tools:

| Tool | Endpoint | Purpose |
|------|----------|---------|
| `search_flights` | `POST /api/v1/webhooks/search-flights` | Search by destination, date, date range, class, price |
| `book_flight` | `POST /api/v1/webhooks/book-flight` | Create a booking |
| `get_booking` | `POST /api/v1/webhooks/get-booking` | Look up booking by reference |
| `cancel_booking` | `POST /api/v1/webhooks/cancel-booking` | Cancel a booking |
| `reschedule_booking` | `POST /api/v1/webhooks/reschedule-booking` | Move booking to new flight |
| `add_extras` | `POST /api/v1/webhooks/add-extras` | Add bags, special items, assistance |
| `query_knowledge` | `POST /api/v1/webhooks/query-knowledge` | Look up airline policies |
| `flight_status` | `POST /api/v1/webhooks/flight-status` | Get scheduled status by flight number |

Webhook tool URLs are updated on the existing agent via PATCH at the start of each loop run (to embed the new ngrok tunnel URL).

---

## Structured Log Output

Each run produces `logs/run_{run_id}.json`:

```json
{
  "run_id": "abc12345",
  "started_at": "2025-01-15T10:00:00Z",
  "iterations": [
    {
      "iteration": 1,
      "scenario_id": "book_next_available",
      "rolled_back": false,
      "evaluation": {
        "scores": {"understanding": 7, "api_correctness": 5, "outcome_confirmation": 6, "naturalness": 8},
        "average": 6.5,
        "overall_pass": false,
        "failures": [
          {
            "criterion": "api_correctness",
            "score": 5,
            "root_cause": "prompt",
            "detail": "Agent did not call book_flight after customer confirmed",
            "quotes": ["I'll look into that for you..."]
          }
        ]
      },
      "changes": {
        "prompt_changed": true,
        "prompt_diff": "--- ...\n+++ ...",
        "code_patches": []
      }
    }
  ],
  "termination_reason": "all_passing",
  "performance_summary": {
    "first_iteration_average": 6.5,
    "final_iteration_average": 8.75,
    "improvement": 2.25,
    "total_iterations": 3
  }
}
```

---

## Running Tests

```bash
make test            # 43 tests
make test-cov        # with coverage report
```

Test categories:
- `test_flight_search.py` — search filters, sort, date range, pagination
- `test_bookings.py` — full booking lifecycle
- `test_booking_consistency.py` — seat constraint enforcement
- `test_webhooks.py` — all ElevenLabs webhook endpoints
- `test_knowledge.py` — all policy topics

---

## Tradeoffs

### What is intentionally simplified

| Decision | Reason |
|----------|--------|
| SQLite instead of Postgres | One developer, one process. Alembic + SQLAlchemy make the swap trivial. |
| JSON knowledge base instead of vector store | Policies are ~1,000 tokens total. Deterministic lookup eliminates hallucination risk from retrieval. |
| In-memory tool call log | Single-run sequential system. Log is accessed cross-process via HTTP endpoints on the API server. |
| Code patching scoped to 4 files | Keeps autonomous patching bounded and safe. |
| No auth on webhooks | Appropriate for assessment. Production: HMAC signature verification on ElevenLabs requests. |

### What is production-inspired

- Database transactions for seat reservation (`with_for_update()` + `CHECK` constraint)
- Alembic migrations from day one
- Two-stage rollback on code patches (test gate + evaluation regression)
- Scenario-locked per-run optimisation with cross-run rotation
- Configurable termination thresholds
- Provider abstraction for zero-friction LLM swap
- Structured JSON logs for auditability

### What would need improvement in a real airline deployment

1. **Postgres** — with read replicas and connection pooling (pgBouncer)
2. **Webhook security** — HMAC signature verification, rate limiting
3. **Auth** — OAuth2 on the booking API; customer identity verification
4. **PII compliance** — passenger names/emails need GDPR-compliant storage and deletion
5. **Real flight data** — GDS integration (Amadeus, Sabre) instead of seeded SQLite
6. **Code patching** — would not exist autonomously in production; refinement loop output is a PR for human review
7. **Observability** — structured logs + metrics (Prometheus/Grafana) + distributed tracing
8. **Concurrent write testing** — against real Postgres with `asyncpg` + `asyncio.gather()`

---

## Configuration Reference

All constants are configurable via `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ELEVENLABS_API_KEY` | required | ElevenLabs authentication |
| `ELEVENLABS_AGENT_ID` | set by `make setup-agent` | Agent to refine (updated in-place each run) |
| `ELEVENLABS_VOICE_ID` | built-in | TTS voice for the agent |
| `NGROK_AUTHTOKEN` | required for loop | Exposes local API to ElevenLabs webhooks |
| `MAX_ITERATIONS` | `5` | Max refinement loop iterations per run |
| `PASS_THRESHOLD` | `8.0` | Score threshold for early termination |
| `MAX_CONVERSATION_TURNS` | `12` | Max turns per simulated conversation |
| `LLM_SIMULATOR` | `ollama/llama3.2` | Model for customer simulation |
| `LLM_EVALUATOR` | `ollama/llama3.2` | Model for transcript evaluation |
| `LLM_PROMPT_FIXER` | `ollama/qwen2.5-coder` | Model for prompt rewriting |
| `LLM_CODE_PATCHER` | `ollama/qwen2.5-coder` | Model for code patching |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama endpoint |
| `API_PORT` | `8000` | FastAPI backend port |
| `UI_PORT` | `8001` | Observer UI port |
| `DATABASE_URL` | `sqlite:///./data/airline.db` | Booking database |
