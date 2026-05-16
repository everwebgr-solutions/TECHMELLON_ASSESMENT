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
    conversation_type: str = Field(
        "booking",
        description="Type of conversation observed: 'booking', 'inquiry', or 'modification'",
    )
    summary: str = Field(
        default="", description="1-3 sentence summary of what went well and what failed."
    )
    overall_pass: bool = Field(
        False, description="True if all criteria scores >= pass threshold"
    )

    @field_validator("conversation_type", mode="before")
    @classmethod
    def normalize_conversation_type(cls, v: object) -> str:
        s = str(v).lower()
        if any(kw in s for kw in ("inquiry", "enquir", "information")):
            return "inquiry"
        if any(kw in s for kw in ("modification", "cancel", "reschedule", "refund", "add_extra", "change")):
            return "modification"
        return "booking"
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
Work through these rules in order and stop at the first match:

1. Read the CUSTOMER GOAL. If it mentions cancelling, refunding, rescheduling, or adding
   extras to an existing booking reference → conversation_type = "modification"

2. Read the CUSTOMER GOAL. If it says "ONLY gathering information" or "NOT booking",
   OR the customer only asked about policies, prices, or availability without intending
   to purchase → conversation_type = "inquiry"

3. Use TOOL CALLS to resolve ambiguous cases:
   - "cancel_booking", "reschedule_booking", or "add_extras" present → "modification"
   - "book_flight" present → "booking"
   - Neither present (only search/lookup tools or empty) → "inquiry"

Output this as the "conversation_type" field in your JSON response.
IMPORTANT: "search_flights" alone never makes a conversation a "booking".

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

MANDATORY PRE-SCORING CHECK — read the TOOL CALLS list before writing any scores:

For each tool that appears in TOOL CALLS:
  → "→ OK": tool SUCCEEDED. Do not claim it failed. Score must reflect success.
  → "→ CONSTRAINT: ...": the backend worked correctly but a business rule blocked the
    action (booking not found, already cancelled, no seats, wrong class, etc.).
    This is NEVER a code failure. It is a prompt failure only if the agent called the
    tool with clearly wrong parameters; otherwise it may simply be an expected state.
  → "→ ERROR: ...": a genuine unexpected backend failure. This is a code failure.
  → Tool not in TOOL CALLS at all: it was never called — prompt failure only.

Apply this check tool by tool. If book_flight → OK appears, you cannot score
api_correctness below 8 on the grounds that the booking failed. If the agent
read a booking reference aloud in the transcript, you cannot claim "reference
was never provided."

ROOT CAUSE — CRITICAL RULES (for any score < 8):

Classify as "code" ONLY when a tool explicitly shows "→ ERROR" in the TOOL CALLS
list AND the inputs to that tool were valid and well-formed.

Classify as "prompt" in ALL other cases, including:
  - A tool was not called when it should have been
  - A tool was called with wrong or missing parameters
  - Agent gave incorrect policy information or skipped a required step
  - Agent misunderstood the customer's request or behaved unnaturally
  - Any ambiguous case — default is always "prompt"

IMPORTANT — "not found" / empty results are almost always a PROMPT failure, not code:
  Only classify as "code" if the tool crashed or returned corrupt data for a valid input
  that should exist based on earlier conversation context.

Default to "prompt" when uncertain. "code" requires an explicit ERROR in TOOL CALLS.

ROOT CAUSE DETAIL FORMAT:
- For "prompt" failures: describe what the agent did wrong and what it should have done.
- For "code" failures: you MUST identify the specific backend function at fault using
  exactly this format on its own line:
    FILE: api/routes/webhooks.py::function_name
  CRITICAL: you may only name a function whose tool name appears in the TOOL CALLS list
  above with an "→ ERROR" result. The mapping from tool name to function name is:
    search_flights  → api/routes/webhooks.py::webhook_search_flights
    book_flight     → api/routes/webhooks.py::webhook_book_flight
    get_booking     → api/routes/webhooks.py::webhook_get_booking
    cancel_booking  → api/routes/webhooks.py::webhook_cancel_booking
    reschedule_booking → api/routes/webhooks.py::webhook_reschedule_booking
    add_extras      → api/routes/webhooks.py::webhook_add_extras
    query_knowledge → api/routes/webhooks.py::webhook_query_knowledge
  If the failing tool is not in TOOL CALLS with an ERROR, classify as "prompt" instead.
  Never name webhook_book_flight unless "book_flight → ERROR" appears in TOOL CALLS.

QUOTING RULES — failure_quotes must be exact substrings of the transcript above.
- Copy the phrase character-for-character from a [AGENT] or [USER] line.
- If you cannot find the exact phrase in the transcript, set failure_quotes to [].
- NEVER write "Booking reference was never provided to the customer" — that is not a
  transcript quote, it is your opinion. If the agent never said the reference, leave
  failure_quotes empty and describe the omission in root_cause_detail instead.
- NEVER write "I'm sorry, I wasn't able to complete your booking due to a system error"
  unless that exact sentence appears word-for-word in the transcript above.
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
        def _fmt_call(c: Dict) -> str:
            args = ', '.join(f'{k}={v}' for k, v in c['inputs'].items())
            if c['success']:
                outcome = 'OK'
            elif c.get('constraint'):
                outcome = f'CONSTRAINT: {c["error"]}'
            else:
                outcome = f'ERROR: {c["error"]}'
            return f"  {c['tool']}({args}) → {outcome}"
        calls_text = "\n".join(_fmt_call(c) for c in tool_calls)
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

    _apply_deterministic_overrides(result, transcript, tool_calls or [])

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


def _apply_deterministic_overrides(
    result: EvaluationResult,
    transcript: List[Dict],
    tool_calls: List[Dict],
) -> None:
    """
    Correct LLM evaluator hallucinations using verifiable transcript evidence.
    Only raises scores — never lowers them — so genuine failures are unaffected.
    """
    import re

    from llm.ollama_provider import _dbg

    # ── API correctness: no tool returned a real ERROR ────────────────────────
    # If the evaluator claims root_cause="code" but no tool call in the log
    # returned an actual ERROR (only OKs and CONSTRAINTs), it is a guaranteed
    # hallucination — the model fabricated a backend failure that didn't happen.
    # We raise api_correctness to 8 (minimum "good") and clear the false claim.
    if result.api_correctness.score < 8 and result.api_correctness.root_cause == "code":
        has_real_error = any(
            not c.get("success") and not c.get("constraint")
            for c in tool_calls
        )
        if not has_real_error:
            _dbg(
                "DETERMINISTIC OVERRIDE",
                f"api_correctness raised to 8: evaluator claimed code failure "
                f"(score {result.api_correctness.score}/10) but no tool in TOOL CALLS "
                f"returned an ERROR — hallucinated failure.",
            )
            result.api_correctness.score = 8
            result.api_correctness.root_cause = "none"
            result.api_correctness.root_cause_detail = (
                "[auto-corrected] No tool returned an ERROR in TOOL CALLS — "
                "evaluator's code failure claim was a hallucination."
            )
            result.api_correctness.failure_quotes = []

    # ── Booking reference confirmation ────────────────────────────────────────
    # Condition: a book_flight call succeeded AND its exact reference appears in
    # an agent turn.  Both must be true — the agent saying "references look like
    # BK-XXXXXX" is not confirmation of an actual booking.
    # We do NOT gate on root_cause_detail keywords because the evaluator often
    # blames webhook_book_flight (code failure) rather than "reference not given",
    # so the keyword guard would suppress the override on hallucinated scores.
    if result.outcome_confirmation.score < 8:
        # Extract the real reference from a successful book_flight tool call.
        # The reference is stored directly in the log entry (added to _log_call).
        confirmed_ref = None
        for call in tool_calls:
            if call.get("tool") == "book_flight" and call.get("success"):
                # Try direct reference field first (stored by _log_call)
                ref = call.get("reference")
                if ref and re.search(r"\bBK-[A-Z0-9]{6}\b", ref):
                    confirmed_ref = ref
                    break
                # Fallback: scan the full string representation
                m = re.search(r"\bBK-[A-Z0-9]{6}\b", str(call))
                if m:
                    confirmed_ref = m.group()
                    break

        if confirmed_ref:
            agent_text = " ".join(
                t["content"] for t in transcript if t.get("role") == "agent"
            )
            if confirmed_ref in agent_text:
                _dbg(
                    "DETERMINISTIC OVERRIDE",
                    f"outcome_confirmation raised to 8: agent spoke exact confirmed "
                    f"reference {confirmed_ref} but evaluator scored "
                    f"{result.outcome_confirmation.score}/10.",
                )
                result.outcome_confirmation.score = 8
                result.outcome_confirmation.root_cause = "none"
                result.outcome_confirmation.root_cause_detail = (
                    f"[auto-corrected] Agent confirmed exact booking reference "
                    f"{confirmed_ref} in transcript — evaluator score overridden."
                )
                result.outcome_confirmation.failure_quotes = []


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
