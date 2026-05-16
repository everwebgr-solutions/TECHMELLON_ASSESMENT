"""
Transcript evaluator — a separate LLM call scores the conversation.

Produces structured EvaluationResult with per-criterion scores,
failure quotes, and root cause classification (prompt vs code).

The evaluator first classifies the conversation type from the transcript
(booking / inquiry / modification) and applies appropriate criteria —
so inquiry-only conversations are never penalised for not making a booking.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from config import PASS_THRESHOLD
from llm.base import LLMMessage, with_retry
from llm.router import get_provider
from refinement.scenarios import Scenario


# ── Output schemas ─────────────────────────────────────────────────────────────

class CriterionScore(BaseModel):
    score: int = Field(..., ge=1, le=10, description="Score from 1 (complete failure) to 10 (perfect)")
    failure_quotes: List[str] = Field(
        default_factory=list,
        description="Exact quotes from transcript showing the failure. Empty if score >= 8.",
    )
    root_cause: str = Field(
        ...,
        description=(
            "'prompt' = agent misunderstood, gave wrong policy, skipped steps; "
            "'code' = API returned wrong data, tool misfired, webhook error; "
            "'none' = no failure"
        ),
    )
    root_cause_detail: str = Field(
        "",
        description="Specific description of the failure cause.",
    )

    @field_validator("root_cause", mode="before")
    @classmethod
    def normalize_root_cause(cls, v: object) -> str:
        """Accept any LLM output and map it to prompt / code / none."""
        s = str(v).lower()
        if "prompt" in s:
            return "prompt"
        if "code" in s or "api" in s or "webhook" in s or "tool" in s:
            return "code"
        return "none"


class EvaluationResult(BaseModel):
    scenario_id: str
    summary: str = Field(
        default="", description="1-3 sentence summary of what went well and what failed."
    )
    overall_pass: bool = Field(
        ..., description="True if all criteria scores >= pass threshold"
    )
    understanding: CriterionScore = Field(
        ..., description="Was the customer's request correctly understood?"
    )
    api_correctness: CriterionScore = Field(
        ..., description="Were the right tools/knowledge-base topics used correctly? Did they return accurate data?"
    )
    outcome_confirmation: CriterionScore = Field(
        ..., description="Was the conversation-appropriate outcome clearly confirmed to the customer?"
    )
    naturalness: CriterionScore = Field(
        ..., description="Was the conversation handled naturally end-to-end? Appropriate tone, no unnecessary loops?"
    )


# ── Evaluator prompt ──────────────────────────────────────────────────────────

_EVALUATOR_SYSTEM = """\
You are an expert evaluator assessing AI airline customer service agent conversations.

STEP 1 — CLASSIFY THE CONVERSATION
Read the transcript and determine what actually happened:
- "booking"      — the customer purchased or tried to purchase a flight ticket
- "inquiry"      — the customer only asked for information (policy, prices, availability);
                   no purchase was intended or attempted
- "modification" — the customer wanted to change, cancel, or add to an existing booking

Use the conversation content to classify, not just the scenario description.

STEP 2 — SCORE ON 4 CRITERIA
Apply the criterion definitions that match the conversation type you identified.

UNDERSTANDING (all types)
  Did the agent correctly identify what the customer wanted and address it?

API_CORRECTNESS
  booking:      Did the agent search flights and create the booking with correct parameters?
                Did it present accurate flight options and prices?
  inquiry:      Did the agent query the correct knowledge-base topic and return ACCURATE
                policy information? Penalise only for wrong facts or wrong topic lookup.
                Do NOT penalise for not making a booking — none was expected.
  modification: Did the agent correctly explain the modification process and, where a
                real booking existed, execute the right API call? If no booking reference
                was available, did it handle that gracefully rather than failing?

OUTCOME_CONFIRMATION
  booking:      Did the agent confirm the booking with a reference number, price, and
                itinerary summary?
  inquiry:      Did the agent clearly answer all of the customer's specific questions?
                Do NOT penalise for absence of a booking reference — none is expected.
  modification: Did the agent confirm either (a) the change was completed, or (b) the
                process and next steps when no real booking was available?

NATURALNESS (all types)
  Was the conversation fluent and natural? Appropriate tone, no unnecessary loops,
  no robotic repetition, handled edge cases gracefully?

SCORING SCALE:
- 9-10: Near perfect. No meaningful issues.
- 7-8:  Good. Minor issues only.
- 5-6:  Acceptable. Some clear failures.
- 3-4:  Poor. Multiple significant failures.
- 1-2:  Failed completely on this criterion.

ROOT CAUSE — CRITICAL RULES (for any score < 8):

Classify as "code" ONLY when there is explicit evidence in the transcript that a backend
tool or webhook malfunctioned — for example:
  - A booking was confirmed but the reference number, price, or flight details are clearly wrong
  - A tool call visibly returned an error when the inputs were valid and well-formatted
  - The agent says it could not complete an action due to a system error

Classify as "prompt" in ALL other cases, including:
  - Agent did not call the right tool or called it with wrong parameters
  - Agent gave incorrect policy information or skipped a required step
  - Agent misunderstood the customer's request
  - Agent behaved unnaturally or repeated itself
  - Any ambiguous case where you cannot see a clear API/tool error

IMPORTANT — "not found" results are almost always a PROMPT failure, not code:
  If a tool returns "not found" or "no results", ask: was the input valid?
  - Customer gave a fictitious/malformed flight number or booking reference → "prompt"
    (the agent should handle gracefully, not loop asking the customer to recheck)
  - Agent called the correct tool with a well-formatted, plausible ID and got "not found" → "prompt"
    (agent should redirect, not blame the system)
  - Only classify as "code" if the tool crashed, returned corrupt data, or rejected a
    correctly-formatted ID that should exist based on earlier conversation context.

Default to "prompt" when uncertain. Only use "code" when the transcript contains
clear, specific evidence of a backend failure — not just a bad or empty result.

ROOT CAUSE DETAIL FORMAT:
- For "prompt" failures: describe what the agent did wrong and what it should have done.
- For "code" failures: you MUST identify the specific backend function at fault using
  exactly this format on its own line:
    FILE: api/routes/webhooks.py::function_name
  Choose from these patchable functions:
    api/routes/webhooks.py::webhook_search_flights
    api/routes/webhooks.py::webhook_book_flight
    api/routes/webhooks.py::webhook_get_booking
    api/routes/webhooks.py::webhook_cancel_booking
    api/routes/webhooks.py::webhook_reschedule_booking
    api/routes/webhooks.py::webhook_add_extras
    api/routes/webhooks.py::webhook_query_knowledge
    api/services/flight_service.py::search_flights
    api/services/flight_service.py::get_flight_by_number
  If the faulty function is not in this list, classify as "prompt" instead.

Be precise. Quote exact phrases from the transcript when scoring below 8.
"""


_MAX_EVAL_TURNS = 18  # keep first 2 + last 16 to stay within local LLM context limits


def _truncate_transcript(transcript: List[Dict]) -> tuple[List[Dict], bool]:
    """Return (truncated_transcript, was_truncated). Keeps head + tail to preserve context."""
    if len(transcript) <= _MAX_EVAL_TURNS:
        return transcript, False
    head = transcript[:2]
    tail = transcript[-((_MAX_EVAL_TURNS - 2)):]
    return head + tail, True


def _evaluator_user_prompt(scenario: Scenario, transcript: List[Dict], tool_calls: List[Dict]) -> str:
    truncated, was_truncated = _truncate_transcript(transcript)
    truncation_note = (
        f"\n[NOTE: Transcript truncated from {len(transcript)} to {len(truncated)} turns "
        f"for context length. First 2 and last {len(truncated) - 2} turns shown.]\n"
        if was_truncated else ""
    )
    transcript_text = "\n".join(
        f"[{t['role'].upper()}]: {t['content']}"
        for t in truncated
    )

    if tool_calls:
        calls_text = "\n".join(
            f"  {c['tool']}({', '.join(f'{k}={v}' for k, v in c['inputs'].items())}) "
            f"→ {'ERROR: ' + c['error'] if not c['success'] else 'OK'}"
            for c in tool_calls
        )
        tool_section = f"\nTOOL CALLS (actual API calls made during this conversation):\n{calls_text}\n"
    else:
        tool_section = "\nTOOL CALLS: none recorded\n"

    return f"""SCENARIO: {scenario['description']}
CUSTOMER GOAL: {scenario['customer_brief']}
{tool_section}
TRANSCRIPT:{truncation_note}
{transcript_text}

Use the TOOL CALLS section as ground truth when evaluating api_correctness and classifying
root causes. If a tool was not called when it should have been, that is a prompt failure.
If a tool was called and returned an ERROR, that is a code failure.

First classify the conversation type from the transcript, then evaluate the AGENT's
performance on all 4 criteria using the definitions appropriate for that type.
For any criterion with score < 8, provide at least one exact failure quote.
"""


# ── Main evaluate function ────────────────────────────────────────────────────

def evaluate_transcript(
    scenario: Scenario,
    transcript: List[Dict],
    tool_calls: Optional[List[Dict]] = None,
) -> EvaluationResult:
    """
    Score a conversation transcript against the scenario criteria.

    tool_calls is the list of actual webhook invocations recorded during the
    simulation (from api.routes.webhooks.get_call_log).  When provided, the
    evaluator can use it as ground truth for api_correctness and root cause
    classification rather than inferring from conversation text alone.
    """
    evaluator_llm = get_provider("evaluator")

    messages = [
        LLMMessage.system(_EVALUATOR_SYSTEM),
        LLMMessage.user(_evaluator_user_prompt(scenario, transcript, tool_calls or [])),
    ]

    from llm.ollama_provider import _dbg
    _dbg("EVALUATOR INPUT", messages[-1]["content"])

    result = with_retry(
        evaluator_llm.complete,
        messages,
        response_schema=EvaluationResult,
        temperature=0.3,
        max_attempts=3,
    )

    # Compute overall_pass based on configured threshold
    result.overall_pass = all(
        criterion.score >= PASS_THRESHOLD
        for criterion in [
            result.understanding,
            result.api_correctness,
            result.outcome_confirmation,
            result.naturalness,
        ]
    )
    result.scenario_id = scenario["id"]

    return result


def scores_dict(result: EvaluationResult) -> Dict[str, int]:
    return {
        "understanding": result.understanding.score,
        "api_correctness": result.api_correctness.score,
        "outcome_confirmation": result.outcome_confirmation.score,
        "naturalness": result.naturalness.score,
    }


def average_score(result: EvaluationResult) -> float:
    scores = scores_dict(result)
    return sum(scores.values()) / len(scores)


def get_prompt_failures(result: EvaluationResult) -> List[CriterionScore]:
    return [
        c for c in [result.understanding, result.api_correctness, result.outcome_confirmation, result.naturalness]
        if c.root_cause == "prompt" and c.score < PASS_THRESHOLD
    ]


def get_code_failures(result: EvaluationResult) -> List[CriterionScore]:
    return [
        c for c in [result.understanding, result.api_correctness, result.outcome_confirmation, result.naturalness]
        if c.root_cause == "code" and c.score < PASS_THRESHOLD
    ]
