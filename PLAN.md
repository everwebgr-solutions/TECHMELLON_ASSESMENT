Promt : 
You are building this assessment as if it were a well-engineered MVP that could realistically evolve into production — NOT as an enterprise-scale platform and NOT as a rushed demo.

Your job is to:

* avoid shortcuts,
* avoid fake implementations,
* avoid brittle hardcoded logic,
* but ALSO avoid unnecessary over-engineering.

The implementation should feel like:

* a strong startup-grade production MVP,
* cleanly architected,
* observable,
* reliable,
* easy to reason about,
* and achievable within assessment scope.

Important philosophy:

* Prefer simple systems that are correct.
* Prefer maintainability over architectural theatrics.
* Use the minimum complexity necessary to build something robust.
* Do not introduce infrastructure unless it clearly solves a real problem in THIS assessment.

Examples:

* A normal relational DB for flights/bookings is correct.
* Seeded fictional flight data is correct.
* A JSON or SQL-backed knowledge base is correct.
* A modular monolith is preferred over microservices.
* Simple background workers are preferred over distributed orchestration.
* Clear logging is preferred over enterprise observability stacks.
* Safe targeted patching is preferred over autonomous unrestricted code rewriting.

Do NOT add:

* Kubernetes
* Kafka
* Event sourcing
* Multi-service distributed systems
* Vector databases unless truly justified
* Complex infra that adds little value to the assessment

Budget and practicality constraints:

* Minimize external API costs.
* Prefer local inference where realistic.
* The architecture must support both local and hosted LLM providers.
* Do not assume unlimited paid API usage.
* The implementation should remain runnable by a developer without significant cloud costs.

LLM strategy requirements:

* Design a provider abstraction layer.
* The system should support:

  * local Ollama models,
  * and optional hosted providers like OpenAI or Anthropic.
* Local models should be the default recommendation for development/testing.
* Hosted APIs should be treated as optional quality upgrades, not hard dependencies.

Recommended approach:

* Use local models for:

  * conversation simulation,
  * evaluation,
  * prompt refinement,
  * and possibly lightweight code patching.
* Use hosted APIs only if clearly justified for patch quality or reasoning reliability.

The architecture should demonstrate:

* good engineering judgment,
* cost awareness,
* reproducibility,
* and provider flexibility.

Suggested local tooling:

* Ollama
* qwen2.5-coder
* deepseek-coder
* llama3
* mistral

The implementation does NOT need:

* custom model training,
* fine-tuning,
* distributed inference,
* GPU orchestration,
* or enterprise AI infrastructure.

The goal is to maximize:

* correctness,
* reliability,
* clarity,
* extensibility,
* and demonstration of engineering judgment.

You must first produce a detailed implementation plan before coding.

The plan should include:

1. Recommended architecture

* Explain the overall structure
* Explain why the chosen complexity level is appropriate
* Explicitly justify why simpler choices are better where applicable

2. Backend design

* API structure
* Database models
* Booking consistency protections
* Webhook handling
* Persistence strategy

3. Knowledge base design

* How policies are stored and retrieved
* Why this approach is sufficient for the assessment
* How hallucinations are prevented

4. LLM provider abstraction
   Design a clean abstraction layer for model providers.

Include:

* provider interface design,
* local provider implementation,
* optional hosted provider implementation,
* model routing strategy,
* retry handling,
* structured output enforcement,
* and testability.

The system should support swapping providers via configuration.

Example philosophy:

* local-first development,
* hosted inference optional.

5. Autonomous refinement loop
   This is the most important part.

Design:

* conversation simulator,
* evaluator,
* failure classification,
* prompt refinement,
* code patching,
* validation,
* rollback protection,
* iteration tracking.

The loop should be realistic and safe.

The evaluator must:

* identify exact failures,
* classify prompt vs code failures,
* produce actionable outputs.

Code patching must:

* only modify targeted files/functions,
* avoid unrestricted arbitrary rewrites,
* run validations/tests before acceptance,
* support rollback if broken.

The refinement loop should be designed so that:

* even smaller/local models can behave reliably,
* prompts are constrained,
* outputs are structured,
* patch scopes are narrow,
* and autonomous behavior remains deterministic and observable.

6. UI dashboard
   Design a lightweight but clean interface showing:

* live conversations,
* evaluation scores,
* iteration history,
* prompt diffs,
* patch history.

Do not overbuild the frontend.

7. Logging & observability
   Design practical structured logging and iteration tracking.
   Focus on debuggability and explainability.

8. Testing strategy
   Include:

* API tests,
* booking consistency tests,
* refinement loop tests,
* regression checks,
* prompt evaluation tests.

9. Project structure
   Provide a clean, maintainable repository layout.

10. Implementation roadmap
    Describe:

* build order,
* milestones,
* dependencies,
* highest-risk areas,
* what to implement first.

11. Engineering tradeoffs
    Explicitly explain:

* what is intentionally simplified,
* what is production-inspired,
* what would need improvement in a real airline deployment,
* and why the current scope is appropriate for the assessment.

Most important:
Demonstrate engineering maturity through good judgment, not through unnecessary complexity.

The implementation should optimize for:

* robustness,
* explainability,
* reproducibility,
* and clarity of engineering decisions,
  NOT architectural spectacle.





Answer : 

Implementation Plan: Airline Voice AI Agent
1. Recommended Architecture
Modular monolith. One Python process serves the API, webhooks, and loop orchestrator. The UI is a separate lightweight server (SSE-based). No microservices, no message queues, no distributed state.

Why this complexity level is appropriate:

The assessment has one developer and one runtime. Microservices add deployment friction without any reliability benefit at this scale.
A monolith is easier to reason about, debug, and demo live.
The hardest part is the refinement loop correctness — not deployment topology.
SQLite covers the persistence needs. Postgres-ready via SQLAlchemy dialect swap.
Top-level components:


FastAPI backend          → flight search, booking CRUD, webhook handlers
Knowledge base service   → JSON-backed policy retrieval
LLM provider layer       → Ollama-first, OpenAI/Anthropic optional
ElevenLabs client        → agent management, Chat Mode conversations
Refinement loop          → simulate → evaluate → fix → push → repeat
UI server                → FastAPI + SSE for real-time observation
2. Backend Design
API Structure
All routes under /api/v1/:

Method	Path	Purpose
GET	/flights/search	Search by destination, date, price, class
GET	/flights/{id}	Flight detail
POST	/bookings	Create booking
GET	/bookings/{ref}	Retrieve by reference
POST	/bookings/{ref}/cancel	Cancel booking
POST	/bookings/{ref}/reschedule	Change flight
POST	/bookings/{ref}/extras	Add baggage / special items
GET	/knowledge/{topic}	Policy lookup
Webhook endpoints (called by ElevenLabs tool use):

Method	Path
POST	/webhooks/search-flights
POST	/webhooks/book-flight
POST	/webhooks/get-booking
POST	/webhooks/cancel-booking
POST	/webhooks/reschedule-booking
POST	/webhooks/add-extras
POST	/webhooks/query-knowledge
Webhooks are thin adapters: they validate input, call the same service layer as the regular API, and return ElevenLabs-compatible JSON. No business logic lives in the webhook layer.

Database Models
SQLite via SQLAlchemy ORM, two tables:


Flight
  id                INTEGER PK
  flight_number     TEXT UNIQUE (e.g. "AX201")
  origin            TEXT
  destination       TEXT
  departure_dt      DATETIME
  arrival_dt        DATETIME
  seat_class        TEXT  (economy | business | first)
  price_gbp         REAL
  total_seats       INTEGER
  available_seats   INTEGER
  created_at        DATETIME

Booking
  id                INTEGER PK
  reference         TEXT UNIQUE (e.g. "BK-A1B2C3")
  flight_id         INTEGER FK → Flight
  passenger_name    TEXT
  passenger_email   TEXT
  seat_preference   TEXT  (window | aisle | extra_legroom | none)
  seat_class        TEXT
  extras            JSON  (baggage list, special items, special assistance)
  status            TEXT  (confirmed | cancelled)
  total_price_gbp   REAL
  created_at        DATETIME
  updated_at        DATETIME
Booking Consistency
Double-booking is prevented by:

available_seats decrement wrapped in a SQLAlchemy serializable transaction with a CHECK (available_seats >= 0) constraint at the DB level.
On conflict (seats = 0), return a clean 409 with a readable message.
Booking references generated as BK- + 6 uppercase alphanumeric chars (UUID-derived, collision-safe at this scale).
No distributed locking needed — SQLite WAL mode handles concurrent writes within one process.

Persistence Strategy
SQLite file at data/airline.db
Alembic for schema migrations (even if only one migration exists — demonstrates the pattern)
Seed script populates ~50 flights across 7 days, 6 destinations, 3 classes
Knowledge base stays as JSON (no DB overhead justified)
3. Knowledge Base Design
Storage: knowledge_base/policies.json — a single structured JSON file with named sections.

Sections:


pet_policy            → species, carrier rules, fees, hold vs cabin, booking requirement
baggage_allowance     → cabin dimensions/weight, hold allowance by class, excess fees
special_assistance    → mobility aid, wheelchair, deaf/blind assistance, booking lead time
check_in_windows      → online open/close, airport counter hours, gate closure
cancellation_refund   → fee tiers by notice period, refund method, non-refundable fares
Retrieval: KnowledgeService.get(topic: str) -> dict returns the full section. The agent prompt instructs the agent to call query-knowledge with a topic name. No fuzzy search, no embeddings — the policies fit in one LLM context comfortably.

Why this is sufficient: The knowledge base is read-only reference data with ~1,000 tokens total. A lookup-by-key approach is deterministic and immune to retrieval hallucinations. A vector DB would add complexity with no meaningful accuracy benefit at this size.

4. LLM Provider Abstraction
Interface

class LLMMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str

class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        response_schema: type[BaseModel] | None = None,
        temperature: float = 0.7,
    ) -> str | BaseModel: ...

    @property
    @abstractmethod
    def name(self) -> str: ...
response_schema triggers structured output mode. If the provider supports JSON schema enforcement (Ollama with format, OpenAI with response_format), it uses it. If not, the implementation wraps the prompt with explicit JSON instructions and parses + validates the output, retrying up to MAX_RETRIES (default 3) on parse failure.

Implementations
OllamaProvider — default for all tasks

Base URL configurable via OLLAMA_BASE_URL (default http://localhost:11434)
Model configurable per task via config
Uses /api/chat endpoint
Structured output via format: "json" + schema description in system prompt
OpenAIProvider — optional quality upgrade

Standard openai SDK
Structured output via response_format={"type": "json_schema", ...}
AnthropicProvider — optional quality upgrade

Standard anthropic SDK
Structured output via XML-delimited JSON in prompt + parse
Model Routing

# config.py
LLM_PROVIDERS = {
    "simulator":        "ollama/llama3.2",
    "evaluator":        "ollama/llama3.2",
    "prompt_fixer":     "ollama/qwen2.5-coder",
    "code_patcher":     "ollama/qwen2.5-coder",
}
LLMRouter.get(task: str) -> LLMProvider reads this map, instantiates the provider, and returns it. Swapping to openai/gpt-4o for any task is a one-line config change.

Retry Handling
Wrapped in a with_retry(provider, messages, schema, max_attempts=3) utility:

On structured output parse failure: retry with error message appended to context
On network error: exponential backoff (1s, 2s, 4s)
On final failure: raise LLMProviderError with full context for logging
5. Autonomous Refinement Loop
This is the highest-weight deliverable. Design priority is correctness and observability over cleverness.

Configurable Constants

MAX_ITERATIONS = 5        # stop after N iterations regardless
PASS_THRESHOLD = 8.0      # all criteria must reach this score to stop early
SCENARIOS = [...]         # list of 10 customer scenarios
Loop Orchestrator (refinement/loop.py)

def run_loop(agent_id: str) -> IterationSummary:
    state = LoopState.load_or_init(agent_id)
    
    for iteration in range(1, MAX_ITERATIONS + 1):
        scenario = select_scenario(state, iteration)
        
        transcript = simulate_conversation(agent_id, scenario)
        evaluation = evaluate_transcript(transcript, scenario)
        
        state.record(iteration, scenario, transcript, evaluation)
        emit_event("evaluation_complete", evaluation)
        
        if all_passing(evaluation):
            break
        
        fixes = plan_fixes(evaluation)
        
        if fixes.prompt_patch:
            new_prompt = apply_prompt_fix(state.current_prompt, fixes.prompt_patch)
            push_prompt_to_elevenlabs(agent_id, new_prompt)
            state.current_prompt = new_prompt
        
        if fixes.code_patches:
            for patch in fixes.code_patches:
                apply_code_patch(patch)   # with rollback protection
        
        emit_event("fixes_applied", fixes)
    
    return state.summarize()
Conversation Simulator (refinement/simulator.py)
An LLM plays a customer with a specific scenario. It sends messages to the ElevenLabs Chat Mode API and collects responses. The customer LLM is given:

The scenario goal
A persona (name, booking reference if relevant)
Instructions to behave naturally but persistently pursue the goal
A MAX_TURNS limit (default 12) to prevent infinite loops
The full exchange is returned as a Transcript (list of {role, content, timestamp} dicts).

ElevenLabs Chat Mode is called via their REST API. Each user turn is sent as a message; the agent's response is captured. The simulator drives this turn-by-turn.

Evaluator (refinement/evaluator.py)
A separate LLM call with a structured output schema:


class CriterionScore(BaseModel):
    score: int                      # 1–10
    failure_quotes: list[str]       # exact quotes from transcript showing the failure
    root_cause: Literal["prompt", "code", "none"]
    root_cause_detail: str          # e.g., "agent failed to call search-flights tool"

class EvaluationResult(BaseModel):
    understanding: CriterionScore   # was the request understood?
    api_correctness: CriterionScore # was the right API called with right params?
    outcome_confirmation: CriterionScore  # was the result clearly confirmed?
    naturalness: CriterionScore     # was the call handled naturally?
    overall_pass: bool
    summary: str
The evaluator prompt is strict: score with evidence, classify root cause, no vague commentary. Because it uses structured output with schema enforcement, even smaller models produce parseable results reliably.

Failure Classification Logic:

prompt — agent misunderstood intent, used wrong phrasing, skipped confirmation, gave wrong policy info
code — tool returned wrong data, booking failed unexpectedly, API returned error, wrong flight shown
none — criterion passed
Prompt Fixer (refinement/prompt_fixer.py)
Input: current system prompt + list of prompt-classified failures with quotes.

The fixer LLM receives:


CURRENT SYSTEM PROMPT:
<prompt>

IDENTIFIED FAILURES (prompt issues only):
- Criterion: understanding | Quote: "..." | Detail: "..."
- ...

Rewrite the system prompt to address these specific failures.
Return ONLY the new system prompt text, no explanation.
Output is validated: must be non-empty, must be longer than 200 chars, must not contain the word "FAILURE" (guard against prompt injection leaking). If validation fails, retain the current prompt and log the skip.

Code Patcher (refinement/code_patcher.py)
This is the most risk-prone component. Design is intentionally constrained:

What the evaluator identifies:


class CodePatchRequest(BaseModel):
    file_path: str           # relative path, e.g., "api/routes/webhooks.py"
    function_name: str       # name of the function to patch
    failure_description: str # what it's currently doing wrong
    expected_behavior: str   # what it should do
What the patcher does:

Read the current function from the file (AST-located by function name)
Send to code patcher LLM with context: function source + failure description + expected behavior
LLM returns only the replacement function body
Safety gates before application:
Python syntax check (compile())
The patch only touches the one named function — AST-verify no other functions are modified
Run pytest tests/test_api.py -x -q — if any test fails, rollback
If all gates pass, write the patched file and reload the FastAPI app (via importlib.reload)
Rollback: Before patching, copy the file to data/patches/backup/{file}_{timestamp}. On any gate failure, restore from backup and log the failed attempt.

Scope constraint: The evaluator prompt explicitly lists only the patchable files:


api/routes/webhooks.py
api/services/booking_service.py
api/services/flight_service.py
knowledge_base/kb_service.py
No arbitrary file is patchable. This keeps autonomous behavior bounded and safe.

State Tracking
LoopState persists to data/runs/{run_id}.json after each iteration. If the loop crashes, it can resume. The state holds the current prompt, patch history, all transcripts, and all evaluation results.

6. UI Dashboard
Technology: FastAPI serves static HTML + vanilla JS. Real-time updates via Server-Sent Events (SSE). No build toolchain, no React, no node_modules.

Why SSE over WebSockets: SSE is one-way (server → client), which matches the "observation only" requirement exactly. Simpler, HTTP-native, works through proxies.

Layout (single page, two columns):


┌─────────────────────────────────────────────────────────────┐
│  Airline AI Refinement Loop — Run ID: abc123                │
│  Iteration 2/5  |  Status: EVALUATING  |  [●] Live         │
├──────────────────────────┬──────────────────────────────────┤
│  LIVE CONVERSATION       │  ITERATION HISTORY               │
│                          │                                  │
│  [Customer] I'd like...  │  Iter 1: Scenario: book_flight   │
│  [Agent]    Certainly... │    understanding:  6/10          │
│  [Customer] Actually...  │    api_correctness: 4/10         │
│  ...                     │    outcome_confirm: 7/10         │
│                          │    naturalness:    8/10          │
│                          │    Root cause: code              │
│                          │                                  │
│                          │  Iter 2: Scenario: reschedule    │
│                          │    [in progress...]              │
├──────────────────────────┴──────────────────────────────────┤
│  PROMPT DIFF (Iteration 1 → 2)                              │
│  - You are an airline assistant...                          │
│  + You are Sky Airways' customer service assistant...       │
│  + Always confirm the booking reference before changes.     │
├─────────────────────────────────────────────────────────────┤
│  CODE PATCHES                                               │
│  ✓ api/services/booking_service.py::reschedule_booking      │
│    "Fixed: was returning old flight details after update"   │
└─────────────────────────────────────────────────────────────┘
The SSE stream emits typed events: conversation_turn, evaluation_complete, prompt_changed, code_patched, iteration_started, loop_complete. The JS handler routes each event type to the correct panel.

7. Logging & Observability
Two output streams:

Console logger — human-readable, colored, per-component prefix:


[LOOP]  Iteration 2 started — scenario: reschedule_booking
[SIM]   Turn 3/12 — customer: "Can you change my date to Friday?"
[EVAL]  api_correctness: 4/10 — root_cause: code
[PATCH] Applying patch to booking_service.py::reschedule_booking
[PATCH] Syntax OK | Tests: 12 passed | Patch accepted
Structured JSON log file — one file per run at logs/run_{run_id}_{timestamp}.json:


{
  "run_id": "...",
  "started_at": "...",
  "iterations": [
    {
      "iteration": 1,
      "scenario": "reschedule_booking",
      "transcript": [...],
      "evaluation": { "scores": {...}, "failures": [...] },
      "changes": {
        "prompt_changed": true,
        "prompt_diff": "...",
        "code_patches": [...]
      }
    }
  ],
  "termination_reason": "all_passing | max_iterations",
  "performance_summary": {
    "first_iteration_avg": 5.75,
    "final_iteration_avg": 8.5,
    "improvement": "+2.75"
  }
}
8. Testing Strategy
Framework: pytest + httpx.AsyncClient (FastAPI TestClient).

Test categories:

Category	What it covers
test_flight_search.py	filter by destination, date, price, class; returns correct results
test_bookings.py	create, retrieve, cancel, reschedule, add extras; correct state transitions
test_booking_consistency.py	concurrent booking requests don't oversell seats (threading test)
test_webhooks.py	each webhook endpoint with valid + invalid payloads
test_knowledge.py	each topic returns correct section; unknown topic returns 404
test_evaluator.py	known good transcript scores ≥8; known bad transcript scores ≤4
test_code_patcher.py	valid patch applied; syntax error patch rejected; test failure rolls back
test_loop.py	mocked LLM + ElevenLabs; loop terminates at max iterations; terminates early on all-passing
All tests run before any code patch is accepted. Tests are the patcher's safety gate.

9. Project Structure

airline-voice-agent/
│
├── api/
│   ├── main.py               # FastAPI app factory
│   ├── db.py                 # SQLAlchemy engine + session
│   ├── models/
│   │   ├── flight.py
│   │   └── booking.py
│   ├── schemas/              # Pydantic request/response schemas
│   │   ├── flight.py
│   │   └── booking.py
│   ├── routes/
│   │   ├── flights.py
│   │   ├── bookings.py
│   │   └── webhooks.py
│   ├── services/
│   │   ├── flight_service.py
│   │   └── booking_service.py
│   └── seed.py               # Seed 50 flights across 7 days
│
├── knowledge_base/
│   ├── policies.json
│   └── kb_service.py
│
├── llm/
│   ├── base.py               # LLMProvider ABC + LLMMessage type
│   ├── ollama_provider.py
│   ├── openai_provider.py
│   ├── anthropic_provider.py
│   ├── router.py             # task → provider mapping
│   └── retry.py              # with_retry utility
│
├── elevenlabs_client/
│   ├── agent.py              # create/update agent, push prompt
│   └── chat.py               # Chat Mode session management
│
├── refinement/
│   ├── loop.py               # main orchestrator
│   ├── simulator.py          # LLM-as-customer
│   ├── evaluator.py          # transcript scoring
│   ├── prompt_fixer.py       # prompt rewrite
│   ├── code_patcher.py       # targeted function patching + rollback
│   ├── state.py              # LoopState persistence
│   └── scenarios.py          # 10 customer scenarios
│
├── ui/
│   ├── server.py             # FastAPI + SSE event stream
│   ├── events.py             # typed event emitter
│   └── static/
│       └── index.html        # single-page dashboard
│
├── tests/
│   ├── conftest.py           # shared fixtures (test DB, mock providers)
│   ├── test_flight_search.py
│   ├── test_bookings.py
│   ├── test_booking_consistency.py
│   ├── test_webhooks.py
│   ├── test_knowledge.py
│   ├── test_evaluator.py
│   ├── test_code_patcher.py
│   └── test_loop.py
│
├── data/
│   ├── airline.db            # SQLite (gitignored)
│   └── patches/backup/       # pre-patch file backups
│
├── logs/                     # structured JSON run logs (gitignored)
│
├── migrations/               # Alembic
│   └── versions/
│
├── config.py                 # all constants, env-backed
├── .env.example
├── requirements.txt
├── Makefile                  # make dev, make test, make seed, make loop
└── README.md
10. Implementation Roadmap
Build order (priority = correctness of the loop, then integration):

Step	Milestone	Approximate effort
1	config.py, .env.example, project skeleton, Makefile	20 min
2	DB models, Alembic migration, seed.py (50 flights)	45 min
3	Knowledge base JSON + kb_service.py	20 min
4	Flight service + routes + schemas	45 min
5	Booking service + routes (create, cancel, reschedule, extras)	60 min
6	Webhook adapter layer	30 min
7	Core API tests + booking consistency test	45 min
8	LLM provider abstraction (Ollama + stubs)	45 min
9	ElevenLabs client (agent management + Chat Mode)	45 min
10	Initial system prompt + ElevenLabs agent setup	30 min
11	Conversation simulator	45 min
12	Evaluator with structured output	60 min
13	Prompt fixer	30 min
14	Code patcher with rollback	60 min
15	Loop orchestrator + LoopState persistence	45 min
16	SSE event emitter + UI server	30 min
17	UI dashboard (HTML/JS)	60 min
18	Structured JSON logging	20 min
19	README + recorded example run	60 min
Highest-risk areas:

ElevenLabs Chat Mode API — must confirm the exact API shape early (step 9); if underdocumented, the simulator falls back to a local mock that replays the agent via direct webhook calls
Code patcher rollback — must be solid before any patch runs autonomously; test this before hooking into the loop
Structured output reliability with local models — use Ollama's format: json and constrained prompts; if a model is too unreliable for evaluation, OpenAI falls in as the evaluator override
Build steps 1–7 before touching the LLM layer — the backend must be independently correct and testable.

11. Engineering Tradeoffs
Intentionally simplified:

SQLite instead of Postgres — correct for one developer and one runtime; Postgres is a dialect swap
JSON knowledge base instead of a vector store — policies are small enough that full-section retrieval is reliable and hallucination-proof
Single-file HTML frontend — avoids build toolchain while meeting all UI requirements
Code patching scoped to a named function list — necessary to keep autonomous behavior bounded and safe
No auth on APIs — appropriate for the assessment; production would require API keys + ElevenLabs signature verification on webhooks
One scenario per iteration (rotating) rather than all 10 in parallel — keeps evaluation focused and loop state simple
Production-inspired:

Database transactions for booking consistency
Alembic migrations from day one
Rollback protection on code patches with test gate
Structured JSON logs for auditability
Configurable termination thresholds
Provider abstraction that makes swap to production LLMs trivial
Would need in a real airline deployment:

Postgres with read replicas for the booking DB
mTLS or HMAC signature verification on ElevenLabs webhooks
Rate limiting on all public endpoints
PII handling (passenger names/emails need GDPR-compliant storage)
Proper auth for the booking APIs (OAuth2 or API keys)
The code patcher would not exist in production — refinement loops there are human-reviewed PRs
Real flight data integration via GDS (Amadeus, Sabre) not a seeded SQLite table
Voice testing in addition to Chat Mode testing
Why current scope is appropriate:
The assessment asks for a working, observable, self-correcting system. Every component above is functional, not faked. The simplifications are honest engineering choices — the smallest sufficient implementation for each concern — not shortcuts that obscure correctness.