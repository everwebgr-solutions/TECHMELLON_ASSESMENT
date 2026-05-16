"""
Transcript evaluator — a separate LLM call scores the conversation.

Produces structured EvaluationResult with per-criterion scores,
failure quotes, and root cause classification (prompt vs code).
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

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
    root_cause: Literal["prompt", "code", "none"] = Field(
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


class EvaluationResult(BaseModel):
    scenario_id: str
    understanding: CriterionScore = Field(
        ..., description="Was the customer's request correctly understood?"
    )
    api_correctness: CriterionScore = Field(
        ..., description="Was the right tool called with correct parameters? Did it return correct data?"
    )
    outcome_confirmation: CriterionScore = Field(
        ..., description="Was the outcome clearly confirmed to the customer (booking ref, price, policy details)?"
    )
    naturalness: CriterionScore = Field(
        ..., description="Was the conversation handled naturally end-to-end? Appropriate tone, no unnecessary loops?"
    )
    overall_pass: bool = Field(
        ..., description="True if all criteria scores >= pass threshold"
    )
    summary: str = Field(
        ..., description="1-3 sentence summary of what went well and what failed."
    )


# ── Evaluator prompt ──────────────────────────────────────────────────────────

_EVALUATOR_SYSTEM = """\
You are an expert evaluator assessing AI airline customer service agent conversations.

Your task: score the agent's performance on 4 criteria, identify exact failures with quotes,
and classify the root cause of each failure.

SCORING GUIDELINES:
- 9-10: Near perfect. No meaningful issues.
- 7-8: Good. Minor issues only.
- 5-6: Acceptable. Some clear failures.
- 3-4: Poor. Multiple significant failures.
- 1-2: Failed completely on this criterion.

ROOT CAUSE CLASSIFICATION:
- "prompt": The agent misunderstood the request, gave incorrect policy information,
  skipped a required step (like confirming before booking), or was poorly instructed.
- "code": A tool/webhook returned wrong data, a booking failed unexpectedly,
  the wrong flight was returned, or an API error occurred.
- "none": The criterion passed (score >= 8).

Be precise. Quote exact phrases. Do not be lenient — this data drives automated fixes.
"""


def _evaluator_user_prompt(scenario: Scenario, transcript: List[Dict]) -> str:
    transcript_text = "\n".join(
        f"[{t['role'].upper()}]: {t['content']}"
        for t in transcript
    )

    return f"""SCENARIO: {scenario['description']}
CUSTOMER GOAL: {scenario['customer_brief']}

TRANSCRIPT:
{transcript_text}

Evaluate the AGENT's performance on all 4 criteria.
For any criterion with score < 8, provide at least one exact failure quote from the transcript.
Classify root cause for each failure as 'prompt', 'code', or 'none'.
"""


# ── Main evaluate function ────────────────────────────────────────────────────

def evaluate_transcript(
    scenario: Scenario,
    transcript: List[Dict],
) -> EvaluationResult:
    """
    Score a conversation transcript against the scenario criteria.
    Returns a fully structured EvaluationResult.
    """
    evaluator_llm = get_provider("evaluator")

    messages = [
        LLMMessage.system(_EVALUATOR_SYSTEM),
        LLMMessage.user(_evaluator_user_prompt(scenario, transcript)),
    ]

    result = with_retry(
        evaluator_llm.complete,
        messages,
        response_schema=EvaluationResult,
        temperature=0.3,  # Low temperature for consistent scoring
        max_attempts=3,
    )

    # Compute overall_pass based on configured threshold
    threshold = int(PASS_THRESHOLD)
    result.overall_pass = all(
        criterion.score >= threshold
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
