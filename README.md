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
# Fill in: ELEVENLABS_API_KEY, and optionally OPENAI_API_KEY or ANTHROPIC_API_KEY
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

### 5. Start the API server

```bash
make dev         # http://localhost:8000
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

### 8. Watch it in real time (optional)

```bash
make ui          # http://localhost:8001
# Open browser → click "Start Loop"
```

---

## Architecture

```
airline-voice-agent/
├── api/                    FastAPI backend — flights, bookings, webhooks
│   ├── models/             SQLAlchemy ORM models (Flight, Booking)
│   ├── schemas/            Pydantic request/response schemas
│   ├── routes/             HTTP route handlers
│   └── services/           Business logic (flight_service, booking_service)
├── knowledge_base/         JSON policy store + lookup service
├── llm/                    Provider abstraction (Ollama, OpenAI, Anthropic)
├── elevenlabs_client/      Agent management + Chat Mode session driver
├── refinement/             The autonomous loop
│   ├── loop.py             Orchestrator
│   ├── simulator.py        LLM-as-customer conversation driver
│   ├── evaluator.py        Structured transcript scoring
│   ├── prompt_fixer.py     Prompt rewriter
│   ├── code_patcher.py     Targeted function-level patching with rollback
│   ├── state.py            Iteration state + JSON log persistence
│   └── scenarios.py        10 customer scenarios
├── ui/                     FastAPI + SSE observer dashboard
└── tests/                  43 pytest tests
```

**Why a modular monolith?** One process, one database, one deployment. The hardest part is the refinement loop logic — not service topology. Microservices would add operational complexity with no reliability benefit at this scale.

---

## APIs and Tools Used

| Tool | Purpose |
|------|---------|
| **ElevenLabs** | Voice agent runtime + Chat Mode API for text-based simulation |
| **FastAPI** | REST API + webhooks + SSE UI server |
| **SQLAlchemy + SQLite** | Booking database with WAL mode and seat constraint enforcement |
| **Alembic** | Schema migrations |
| **Ollama** | Local LLM provider (llama3.2, qwen2.5-coder) — default, no cost |
| **OpenAI / Anthropic** | Optional hosted providers for higher evaluation quality |
| **Pydantic v2** | Structured output schemas for evaluator and all API models |
| **pytest** | 43 tests covering API, consistency, webhooks, knowledge base |

---

## LLM Provider Strategy

The system uses a provider abstraction layer. Each task routes to a configurable model:

```
LLM_SIMULATOR=ollama/llama3.2       # customer roleplay
LLM_EVALUATOR=ollama/llama3.2       # transcript scoring
LLM_PROMPT_FIXER=ollama/qwen2.5-coder
LLM_CODE_PATCHER=ollama/qwen2.5-coder
```

**Default: Ollama (local, free).** Swap any task to OpenAI or Anthropic by changing one line in `.env`:

```bash
LLM_EVALUATOR=openai/gpt-4o         # higher consistency on structured scoring
LLM_CODE_PATCHER=anthropic/claude-sonnet-4-6  # stronger code reasoning
```

---

## Refinement Loop Design

### Cycle (per iteration)

1. **Simulate** — An LLM plays a customer with one of 10 scenarios. Drives the ElevenLabs agent via Chat Mode API (text, no audio). Up to 12 turns.
2. **Evaluate** — A separate LLM call scores the transcript on 4 criteria (1–10 each) with structured output enforcement. Classifies each failure as `prompt` or `code`.
3. **Fix** — If prompt failures: LLM rewrites system prompt targeting the specific failures. If code failures: LLM generates a targeted patch for the identified function.
4. **Push** — Updated prompt sent to ElevenLabs via REST API.
5. **Repeat** — Until all scores ≥ `PASS_THRESHOLD` or `MAX_ITERATIONS` reached.

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
- **Rollback**: Backup created before every patch; restored automatically if any gate fails

---

## Evaluation Criteria

Each conversation is scored on:

| Criterion | What it measures |
|-----------|-----------------|
| `understanding` | Was the customer's request correctly understood? |
| `api_correctness` | Was the right tool called with correct parameters? |
| `outcome_confirmation` | Was the outcome clearly confirmed to the customer? |
| `naturalness` | Was the call handled naturally end-to-end? |

Root cause classification: `prompt` (agent behaviour issue) or `code` (API/webhook issue).

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
      "evaluation": {
        "scores": {"understanding": 7, "api_correctness": 5, ...},
        "average": 6.25,
        "overall_pass": false,
        "failures": [...]
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
    "first_iteration_average": 6.25,
    "final_iteration_average": 8.75,
    "improvement": 2.5,
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
- `test_flight_search.py` — search filters, sort, pagination
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
| Single-file HTML frontend | No build toolchain. SSE is one-way (matches "observation only" requirement). |
| Sequential consistency test instead of threading | SQLite serialises writes by design. A thread test would add OS non-determinism without testing more constraint code. |
| Code patching scoped to 4 files | Keeps autonomous patching bounded and safe. |
| No auth on webhooks | Appropriate for assessment. Production: HMAC signature verification on ElevenLabs requests. |

### What is production-inspired

- Database transactions for seat reservation (`with_for_update()` + `CHECK` constraint)
- Alembic migrations from day one
- Rollback protection on code patches with full test gate
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
| `MAX_ITERATIONS` | `5` | Max refinement loop iterations |
| `PASS_THRESHOLD` | `8.0` | Score threshold to stop early |
| `MAX_CONVERSATION_TURNS` | `12` | Max turns per simulated conversation |
| `LLM_SIMULATOR` | `ollama/llama3.2` | Model for customer simulation |
| `LLM_EVALUATOR` | `ollama/llama3.2` | Model for transcript evaluation |
| `LLM_PROMPT_FIXER` | `ollama/qwen2.5-coder` | Model for prompt rewriting |
| `LLM_CODE_PATCHER` | `ollama/qwen2.5-coder` | Model for code patching |
| `API_PORT` | `8000` | FastAPI backend port |
| `UI_PORT` | `8001` | Observer UI port |
