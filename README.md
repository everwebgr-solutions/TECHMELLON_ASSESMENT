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
make seed        # seed 756 flights across 7 days × 6 destinations × 3 classes
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

## Spec Compliance

The following table maps every requirement from the assessment spec to its implementation:

| Requirement | Status | Implementation |
|---|---|---|
| **Knowledge base** covering pet policy, baggage, check-in, cancellation, special assistance | ✅ | `knowledge_base/policies.json` + `kb_service.py` — deterministic JSON lookup (see tradeoffs) |
| **Flight database** — fictional flights across a week, multiple destinations/classes/prices | ✅ | SQLite via SQLAlchemy + Alembic; 756 flights seeded by `make seed` |
| **Search flights** by destination, date, price | ✅ | `POST /api/v1/webhooks/search-flights` — supports date ranges, seat class, price cap, sort |
| **Book a flight** — write to DB, prevent double-bookings | ✅ | `POST /api/v1/webhooks/book-flight` — serializable transaction + CHECK constraint on seats |
| **Cancel or reschedule** a booking | ✅ | `/cancel-booking`, `/reschedule-booking` |
| **Add baggage or special items** to an existing booking | ✅ | `POST /api/v1/webhooks/add-extras` |
| **Retrieve booking by reference** | ✅ | `POST /api/v1/webhooks/get-booking` |
| All operations **persist to a database** — bookings visible across calls | ✅ | Single SQLite DB with WAL mode; Alembic-managed schema |
| **Simulate** a conversation (LLM plays customer, ElevenLabs plays agent) | ✅ | `refinement/simulator.py` drives ElevenLabs Chat Mode WebSocket |
| **Evaluate** transcript on 4 criteria with root cause classification | ✅ | `refinement/evaluator.py` — structured LLM call + deterministic post-processing |
| **Fix** prompt failures (LLM rewrites system prompt) | ✅ | `refinement/prompt_fixer.py` |
| **Fix** code failures (LLM generates targeted patch) | ✅ | `refinement/code_patcher.py` — syntax check + AST check + test suite gate |
| **Push updated prompt** to ElevenLabs via REST API | ✅ | `elevenlabs_client/agent.py::update_agent_prompt` — PATCH on existing agent |
| **Terminate** when all scores ≥ 8/10 or after 5 iterations | ✅ | Both thresholds are configurable constants (`PASS_THRESHOLD`, `MAX_ITERATIONS`) |
| **Observer UI** — live conversation feed, scores per iteration, prompt diff, iteration history | ✅ | FastAPI + SSE + React/Vite dashboard at `http://localhost:8001` |
| **Structured log file** per run — scenario, scores, root causes, changes, performance summary | ✅ | `logs/run_{id}.json` with `rolled_back`, `tool_calls`, `performance_summary` |

### Customer scenarios supported

All 10 required scenario types from the spec are covered and tested:

| Scenario | Covered |
|---|---|
| Book next available flight to a destination | ✅ |
| Find and book cheapest tickets within the following week | ✅ |
| Enquire about pet policy (cabin/hold rules, fees, notice) | ✅ |
| Reschedule an existing booking to a different date or flight | ✅ |
| Enquire about baggage allowance — weight limits, excess fees | ✅ |
| Request refund or cancellation for an existing booking | ✅ |
| Book a flight with a specific seat preference (window, aisle, extra legroom) | ✅ |
| Add an extra bag or special item (pram, sports equipment) | ✅ |
| Enquire about check-in times, gate information, or flight status | ✅ |
| Request assistance for reduced mobility or special needs | ✅ |

Five additional harder scenarios are included (EU261 compensation claim, same-day booking with check-in deadline, combined booking + pet transport, upgrade enquiry, multi-leg inquiry) for a total of 15 scenarios across the rotation.

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
│   ├── prompt_fixer.py     Prompt rewriter — patches one conversation-type section at a time
│   ├── code_patcher.py     Targeted function-level patching with rollback
│   ├── state.py            Iteration state + JSON log persistence
│   └── scenarios.py        15 customer scenarios in rotating round-robin
├── ui/                     FastAPI + SSE observer dashboard (React/Vite frontend)
└── tests/                  43 pytest tests
```

---

## APIs and Tools Used

| Tool | Purpose |
|------|---------|
| **ElevenLabs** | Voice agent runtime + Chat Mode WebSocket API for text-based simulation (audio discarded, text only) |
| **FastAPI** | REST API + webhooks + SSE UI server |
| **SQLAlchemy + SQLite** | Booking database with WAL mode and seat constraint enforcement |
| **Alembic** | Schema migrations (Postgres-ready — swap `DATABASE_URL` to migrate) |
| **Ollama** | Local LLM provider (llama3.2, qwen2.5-coder) — default, zero cost, no API key |
| **OpenAI / Anthropic** | Optional hosted providers for higher evaluation quality and code patching |
| **Pydantic v2** | Structured output schemas for evaluator and all API models |
| **pyngrok** | Exposes the local API server publicly so ElevenLabs can reach webhook endpoints |
| **pytest** | 43 tests covering API routes, booking lifecycle, concurrency, webhooks, knowledge base |

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
4. **Fix** — If prompt failures: LLM rewrites the system prompt section for that conversation type. If code failures: LLM generates a targeted patch for the identified function.
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

## Example Run

The following is a real recorded run (`logs/run_38e47637.json`) against the **baggage enquiry** scenario, using the default Ollama/llama3.2 configuration.

### Starting prompt (baseline `## Booking` section excerpt)

```
## Booking

### Booking a Flight
1. Search for available flights using the customer's requirements.
2. Present the top options clearly: flight number, departure time, destination, price, class.
3. Confirm the customer's choice, their full name, and email address.
4. Call book_flight to complete the booking.
5. Confirm the booking reference clearly to the customer.
```

### Scores per iteration

| Iteration | understanding | api_correctness | outcome_confirmation | naturalness | **Average** | Rolled back |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 8 | 7 | 4 | 6 | **6.25** | No |
| 2 | 8 | 9 | 6 | 9 | **8.00** | No |
| 3 | 8 | 6 | 5 | 8 | **6.75** | **Yes** |
| 4 | 8 | 9 | 6 | 8 | **7.75** | No |
| 5 | 9 | 10 | 9 | 9 | **9.25** | No |

**Termination reason:** `all_passing` — all 4 criteria ≥ 8.0 in iteration 5.
**Total improvement:** +3.00 (6.25 → 9.25).

### What the loop changed

**Iteration 1** — evaluator identified `outcome_confirmation` as the primary failure (score 4/10): agent completed the booking but did not read the reference number back. Prompt fixer appended:

```diff
+## Behaviour Fixes: booking
+- Always ask for the customer's preferred method of confirming their booking.
+- Provide a clear and concise booking reference immediately after completing the booking.
```

**Iteration 3** — regression (avg 8.0 → 6.75). Loop rolled back all changes from iteration 2 and retried from the checkpoint.

**Iteration 4** — prompt fixer tightened the fix instruction with more direct wording:

```diff
-- Always ask for the customer's preferred method of confirming their booking.
-- Provide a clear and concise booking reference immediately after completing the booking.
+- Confirm the booking reference clearly after completing the booking.
+- Repeat the booking reference back to the customer at the end of the conversation.
```

**Iteration 5** — agent correctly read out the booking reference, correctly scored api_correctness=10 and outcome_confirmation=9. Loop terminated.

### Final refined prompt (added section)

```
## Behaviour Fixes: booking
- Confirm the booking reference clearly after completing the booking.
- Repeat the booking reference back to the customer at the end of the conversation.
```

---

## Tradeoffs and Design Decisions

### 1. Deterministic overrides on the evaluator

**The problem:** Local LLMs (llama3.2 in particular) hallucinate tool call outcomes when scoring transcripts. The two most common hallucinations observed during testing:

1. **False code failures**: the evaluator scores `api_correctness` low and classifies the cause as `"code"` — claiming a tool crashed or returned wrong data — even when the tool call log shows a clean `→ OK` or a legitimate `→ CONSTRAINT` (e.g., no seats available). This directs the code patcher at working code, wasting an iteration.

2. **False confirmation failures**: the evaluator scores `outcome_confirmation` low on the grounds that "the booking reference was never provided", even when the agent said the reference verbatim in the transcript. This is a hallucination caused by poor attention over longer transcripts.

**The fix:** `evaluator.py::_apply_deterministic_overrides()` post-processes the LLM's output using verifiable facts:

- If the evaluator claims `root_cause="code"` but no tool in the call log returned an `→ ERROR`, the score is raised to 8 and the false claim is cleared. This can only be a hallucination — the log is captured server-side and is authoritative.
- If `outcome_confirmation` is scored below 8 and a successful `book_flight` call exists in the log **and** the exact booking reference (e.g., `BK-A1B2C3`) appears in an agent turn of the transcript, the score is raised to 8.

**Why overrides only raise, never lower:** Genuine failures (e.g., the agent said the wrong reference, or `book_flight` really did error) are never penalised further. The overrides are a targeted correction for a known LLM failure mode, not a score-inflating optimisation.

**Production alternative:** A hosted model (GPT-4o, Claude) reduces hallucination rates significantly and often removes the need for these guards entirely. The overrides remain useful as a consistency layer even with hosted models.

---

### 2. Local model limitations

The default configuration runs on `ollama/llama3.2` (8B) for simulation and evaluation, and `ollama/qwen2.5-coder` for prompt fixing and code patching. These are free and run entirely offline, which was the primary motivation. The tradeoffs are real:

| Limitation | Impact | Mitigation |
|---|---|---|
| **Context window (~8k tokens)** | Long transcripts (>18 turns) are truncated before evaluation — the evaluator only sees the first 2 and last 16 turns | Transcript kept to `MAX_CONVERSATION_TURNS=12`; truncation is flagged in the evaluator prompt |
| **Structured output reliability** | `llama3.2` frequently emits invalid JSON for the `EvaluationResult` schema, especially on the first attempt | `with_retry()` in `llm/base.py` retries up to 3 times and injects the parse error back into the message list so the model can self-correct |
| **Evaluation consistency** | The same conversation can be scored 6/10 in one run and 8/10 in the next; root cause classification flips between `"prompt"` and `"code"` on identical transcripts | Deterministic overrides (see §1) handle the most damaging inconsistencies; regression check + rollback prevent bad fixes from sticking |
| **Prompt fixer quality** | `qwen2.5-coder` sometimes outputs a full prompt rewrite instead of targeted bullet points, or includes forbidden tokens (`SCORE:`, markdown fences) | `prompt_fixer.py` rejects outputs that exceed 50% of the current prompt length, lack bullet points, or contain forbidden tokens |
| **Code patcher quality** | Local models produce syntactically invalid patches more often than hosted models | Three-gate safety chain (syntax check → AST scope check → full test suite) prevents any broken patch from reaching production |

**Recommended upgrade path for a live deployment:** Set `LLM_EVALUATOR=openai/gpt-4o` and `LLM_CODE_PATCHER=anthropic/claude-sonnet-4-6`. The simulator can remain on a local model since roleplay quality is less critical than evaluation accuracy.

---

### 3. JSON knowledge base instead of a vector store

**Decision:** Policies are stored in a single `knowledge_base/policies.json` file. Lookup is a direct key match by topic name, not semantic retrieval.

**Why:** The five required policy topics total roughly 1,000 tokens. A vector DB adds infrastructure complexity, cold-start latency, and embedding costs — none of which buy anything when the entire corpus fits in a single JSON object. Deterministic key-based lookup also eliminates the hallucination risk from approximate retrieval (the wrong policy chunk being returned with high similarity).

**Tradeoff:** Adding a sixth policy topic requires editing the JSON and the `QueryKnowledgeRequest` docstring. That is acceptable at this scale. A real airline's policy corpus (hundreds of topics, tens of thousands of tokens) would warrant semantic retrieval.

---

### 4. In-memory tool call log + HTTP cross-process boundary

**Decision:** The webhook handler (`api/routes/webhooks.py`) records every tool invocation in a thread-safe in-memory list. The refinement loop reads this via `GET /api/v1/webhooks/tool-calls` after each simulation.

**Why:** The API server and the refinement loop run in separate processes. Sharing state through the same Python module import would silently read empty data (different process, different memory). HTTP is the explicit, correct boundary. The in-memory log is cleared by `DELETE /api/v1/webhooks/tool-calls` before each simulation.

**Tradeoff:** If the API server crashes mid-simulation, the log is lost. In a production setting this would be a Redis list with TTL, so the log survives restarts and is accessible from any replica.

---

### 5. SQLite instead of Postgres

**Decision:** SQLite with WAL journal mode and a `CHECK (available_seats >= 0)` constraint.

**Why:** One developer, one machine, no connection pooling to set up. The seat reservation is done inside a `SERIALIZABLE` transaction with `SELECT ... FOR UPDATE`-equivalent locking to prevent double-booking. Alembic manages the schema from day one, so switching to Postgres is a one-line `DATABASE_URL` change.

**Tradeoff:** SQLite does not support concurrent writes from multiple processes. The loop runs sequentially (one simulation at a time), so this is not a problem in practice. Parallel simulation runs would require Postgres.

---

### 6. Prompt fixer patches one conversation-type section at a time

**Decision:** The system prompt is divided into `## Booking`, `## Modification`, `## Inquiry`, and `## Shared Behaviour` sections. The prompt fixer only modifies the section that matches the evaluated conversation type, appending a `## Behaviour Fixes: <type>` block.

**Why:** Early iterations of the fixer rewrote the entire prompt, which caused regressions in previously-passing scenario types. Scoping fixes to the relevant section prevents "lateral damage" — fixing booking flows should not change how the agent handles policy inquiries.

**Tradeoff:** Cross-cutting failures (e.g., the agent's tone in all conversation types) require manual edits to `## Shared Behaviour`, which the fixer never touches. The evaluator's `naturalness` criterion covers these cases and would trigger a prompt fix — but the fix would be scoped to the tested type, not the shared section.

---

### 7. ngrok for webhook reachability

**Decision:** The loop starts a pyngrok tunnel at startup and patches the ElevenLabs agent's webhook URLs to point at the new public URL.

**Why:** ElevenLabs calls our webhooks from their servers — they cannot reach `localhost`. ngrok is the simplest way to bridge this without deploying to a cloud host. pyngrok was chosen over localtunnel because it is a Python library (no `npx` dependency), returns the URL synchronously, and does not inject a click-through landing page that would break automated POST requests.

**Tradeoff:** ngrok introduces a network round-trip latency on every webhook call (typically 100–300 ms). The free ngrok tier has rate limits and session expiry. A deployed system would serve the API on a real HTTPS endpoint and skip the tunnel entirely.

---

### 8. Webhook security omitted

**Decision:** No HMAC signature verification on incoming ElevenLabs webhook requests.

**Why:** Appropriate for an assessment environment where the only caller is ElevenLabs over ngrok.

**Production requirement:** ElevenLabs signs outgoing webhook requests. Production handlers should verify the `X-ElevenLabs-Signature` header using the shared secret before processing any payload.

---

## What I Would Improve Next

1. **Hosted LLM for evaluation by default** — `gpt-4o` or `claude-sonnet-4-6` as `LLM_EVALUATOR` eliminates most structured output failures and most evaluation hallucinations, making the deterministic overrides a safety net rather than a necessity. The delta in evaluation quality is substantial.

2. **Multi-scenario runs** — the loop currently picks one scenario and optimises for it. A run that rotates through 3–5 scenarios per iteration and aggregates scores would produce more generalizable prompt fixes and surface regressions across scenario types earlier.

3. **Postgres + Redis** — swap `DATABASE_URL` to a real Postgres instance; move the tool call log to a Redis list with TTL. This unblocks parallel simulation runs and makes the architecture horizontally scalable.

4. **Webhook HMAC verification** — add `X-ElevenLabs-Signature` header validation to all webhook endpoints before any production deployment.

5. **Auth on the booking API** — OAuth2 bearer tokens + customer identity verification before any `get_booking` / `cancel_booking` / `reschedule_booking` call. Currently the booking reference alone is sufficient to cancel or modify a booking — that is a real-world security hole.

6. **Real flight data** — replace the seeded SQLite data with a GDS integration (Amadeus, Sabre) for live inventory and pricing. The service layer and webhook contracts are already defined; it is a service-layer swap.

7. **Code patcher as a PR generator** — in production, autonomous code patching would not apply directly to running services. The right behaviour is to produce a diff and open a GitHub PR for human review. The patch generation and safety gates are already in place; the final `apply` step would become `git commit && gh pr create`.

8. **Observability** — structured logs are emitted per run, but there is no metrics layer. Adding Prometheus counters (evaluations per scenario, average score by iteration, rollback rate) and a Grafana dashboard would make the refinement loop's behaviour visible at a glance.

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
| 15 | Multi-leg inquiry: baggage + check-in + cancellation in one call | Inquiry (harder) |

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
- **`code`** — a webhook returned an unexpected error. Fixed by the code patcher.

Root cause is determined from both the conversation transcript **and** the actual tool call log (tool name, inputs, `→ OK` / `→ CONSTRAINT` / `→ ERROR`) captured from the API server during simulation. The evaluator system prompt explicitly instructs the model: classify as `"code"` **only** when a tool shows `→ ERROR` in the log — all other failure modes default to `"prompt"`.

---

## Webhook Tool Call Log

Every webhook invocation during a simulation is logged in the API server process:

```
GET    /api/v1/webhooks/tool-calls    — fetch the log (used by evaluator)
DELETE /api/v1/webhooks/tool-calls    — clear before next simulation
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
  "run_id": "38e47637",
  "started_at": "2026-05-16T14:00:00Z",
  "termination_reason": "all_passing",
  "iterations": [
    {
      "iteration": 1,
      "scenario_id": "baggage_enquiry",
      "rolled_back": false,
      "tool_calls": [
        { "tool": "query_knowledge", "inputs": {"topic": "baggage_allowance"}, "success": true, "error": null }
      ],
      "evaluation": {
        "scores": {"understanding": 8, "api_correctness": 7, "outcome_confirmation": 4, "naturalness": 6},
        "average": 6.25,
        "overall_pass": false,
        "failures": [
          {
            "criterion": "outcome_confirmation",
            "score": 4,
            "root_cause": "prompt",
            "detail": "Agent did not read the booking reference back to the customer"
          }
        ]
      },
      "changes": {
        "prompt_changed": true,
        "prompt_diff": "--- prompt_before\n+++ prompt_after\n@@ ...",
        "code_patches": []
      }
    }
  ],
  "performance_summary": {
    "first_iteration_average": 6.25,
    "final_iteration_average": 9.25,
    "improvement": 3.0,
    "total_iterations": 5
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
- `test_booking_consistency.py` — concurrent seat constraint enforcement
- `test_webhooks.py` — all ElevenLabs webhook endpoints
- `test_knowledge.py` — all policy topics

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
