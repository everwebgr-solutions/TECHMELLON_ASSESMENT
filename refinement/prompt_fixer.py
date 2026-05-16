"""
Prompt fixer — patches the system prompt to address identified failures.

Strategy: patch-only, not full-rewrite.
  - The base prompt is never regenerated — only a short targeted fix block is produced.
  - Any previous fix block (## Behaviour Fixes section) is stripped and replaced.
  - The LLM only needs to output a handful of bullet-point instructions (~50-400 chars),
    well within the output limit of any local model.
"""
from __future__ import annotations

import re
from typing import List

from llm.base import LLMMessage, with_retry
from llm.router import get_provider
from refinement.evaluator import CriterionScore

_FIX_SECTION_HEADER = "## Behaviour Fixes"
_FIX_SECTION_RE = re.compile(
    r"\n+" + re.escape(_FIX_SECTION_HEADER) + r".*$",
    re.DOTALL,
)

_FIXER_SYSTEM = """\
You are an expert prompt engineer for an AI airline customer service agent.

Your task: given a list of specific failures observed in a conversation, write a SHORT
set of additional behavioural instructions to fix those failures.

Rules:
1. Output ONLY the new instructions — 2 to 6 bullet points, each starting with "- "
2. Each bullet must be a concrete, actionable rule the agent can follow
3. Do not repeat instructions already obvious from context
4. Do not output explanations, headings, preamble, markdown fences, or anything other
   than the bullet points themselves
5. Keep the total output under 400 characters
6. Focus on WHAT the agent should DO differently, not on describing the failure
"""


def _strip_fix_block(prompt: str) -> str:
    """Remove any previously appended ## Behaviour Fixes section."""
    return _FIX_SECTION_RE.sub("", prompt).rstrip()


def rewrite_prompt(
    current_prompt: str,
    failures: List[CriterionScore],
) -> str:
    """
    Patch the system prompt by appending a targeted fix block.

    The base prompt is preserved intact. Any previous fix block is replaced
    with one generated from the current iteration's failures.

    Returns current_prompt unchanged if no valid fix block is produced.
    """
    if not failures:
        return current_prompt

    base_prompt = _strip_fix_block(current_prompt)

    failure_descriptions = "\n".join(
        f"- Criterion failed (score {f.score}/10): {f.root_cause_detail}\n"
        f"  Exact quotes from transcript:\n"
        + (
            "\n".join(f'    > "{q}"' for q in f.failure_quotes)
            if f.failure_quotes
            else "    (no quotes provided)"
        )
        for f in failures
    )

    user_content = (
        f"FAILURES TO FIX:\n{failure_descriptions}\n\n"
        f"Write 2-6 bullet-point instructions (starting with '- ') that tell the agent "
        f"exactly what to do differently. Output ONLY the bullet points."
    )

    fixer_llm = get_provider("prompt_fixer")
    messages = [
        LLMMessage.system(_FIXER_SYSTEM),
        LLMMessage.user(user_content),
    ]

    from llm.ollama_provider import _dbg
    _dbg("PROMPT FIXER INPUT", user_content)

    try:
        fix_block: str = with_retry(
            fixer_llm.complete,
            messages,
            temperature=0.3,
            max_attempts=3,
        )
    except Exception as exc:
        _dbg("PROMPT FIXER FAILED", str(exc))
        return current_prompt

    fix_block = fix_block.strip()
    _dbg("PROMPT FIXER OUTPUT (raw)", fix_block)

    # Validation gates
    if not fix_block:
        return current_prompt

    # Must contain at least one bullet point
    if not any(line.strip().startswith("- ") for line in fix_block.splitlines()):
        _dbg("PROMPT FIXER REJECTED — no bullet points found", fix_block)
        return current_prompt

    # Sanity ceiling — if the model output the whole prompt again, reject it
    if len(fix_block) > len(base_prompt) * 0.5:
        _dbg("PROMPT FIXER REJECTED — output suspiciously long (possible full rewrite)", fix_block[:200])
        return current_prompt

    # Guard: reject if the fix block contains evaluator-injected artifacts
    forbidden = ["FAILURE:", "ROOT CAUSE:", "SCORE:", "```"]
    if any(token in fix_block for token in forbidden):
        _dbg("PROMPT FIXER REJECTED — forbidden tokens found", fix_block[:200])
        return current_prompt

    new_prompt = f"{base_prompt}\n\n{_FIX_SECTION_HEADER}\n{fix_block}"
    _dbg("PROMPT FIXER FINAL PROMPT (last 400 chars)", new_prompt[-400:])
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
