"""
Prompt fixer — rewrites the system prompt to address identified failures.

Only called when the evaluator classifies failures as root_cause='prompt'.
The rewrite targets the specific failure descriptions and quotes.
"""
from __future__ import annotations

from typing import List

from llm.base import LLMMessage, with_retry
from llm.router import get_provider
from refinement.evaluator import CriterionScore

_FIXER_SYSTEM = """\
You are an expert prompt engineer for an AI airline customer service agent.
Your task: rewrite a system prompt to fix specific identified failures.

Rules:
1. Keep everything that works — only fix what is broken
2. Be surgical: add or clarify instructions to address each listed failure
3. The new prompt must be complete and self-contained (the old prompt is replaced entirely)
4. Do not add unnecessary complexity or padding
5. Maintain the same structure and tone as the original
6. The prompt must be at least 300 characters long
7. Output ONLY the new system prompt text — no explanation, no preamble, no markdown
"""


def rewrite_prompt(
    current_prompt: str,
    failures: List[CriterionScore],
) -> str:
    """
    Produce an improved system prompt that addresses the listed prompt failures.

    Args:
        current_prompt: The current system prompt in use
        failures: List of CriterionScore objects with root_cause='prompt'

    Returns:
        The new system prompt string.
        Returns current_prompt unchanged if no valid rewrite is produced.
    """
    if not failures:
        return current_prompt

    failure_descriptions = "\n".join(
        f"- Criterion failed (score {f.score}/10): {f.root_cause_detail}\n"
        f"  Failure quotes: {'; '.join(f.failure_quotes) if f.failure_quotes else 'none provided'}"
        for f in failures
    )

    user_content = f"""CURRENT SYSTEM PROMPT:
{current_prompt}

IDENTIFIED FAILURES (prompt issues to fix):
{failure_descriptions}

Rewrite the system prompt to fix these specific failures while keeping everything else.
Output ONLY the new system prompt — nothing else."""

    fixer_llm = get_provider("prompt_fixer")
    messages = [
        LLMMessage.system(_FIXER_SYSTEM),
        LLMMessage.user(user_content),
    ]

    new_prompt: str = with_retry(
        fixer_llm.complete,
        messages,
        temperature=0.4,
        max_attempts=3,
    )

    new_prompt = new_prompt.strip()

    # Validation gates
    if len(new_prompt) < 300:
        return current_prompt  # reject — too short, likely malformed

    if new_prompt == current_prompt:
        return current_prompt  # no change

    # Guard: reject if prompt contains evaluator-injected artifacts
    forbidden = ["FAILURE:", "ROOT CAUSE:", "SCORE:", "```json"]
    if any(token in new_prompt for token in forbidden):
        return current_prompt

    return new_prompt


def compute_diff(old_prompt: str, new_prompt: str) -> str:
    """Return a unified-style diff of the two prompts for display."""
    import difflib

    old_lines = old_prompt.splitlines(keepends=True)
    new_lines = new_prompt.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile="prompt_before",
        tofile="prompt_after",
        lineterm="",
    )
    return "".join(diff)
