"""
Prompt fixer — surgically patches one conversation-type section of the system prompt.

The system prompt is divided into named sections:
  ## Booking | ## Modification | ## Inquiry | ## Shared Behaviour

Each run the fixer:
  1. Receives the conversation_type ('booking', 'inquiry', 'modification') from the evaluator.
  2. Extracts only the matching section to give the LLM focused context.
  3. Generates a short fix block targeting that section's behaviour.
  4. Replaces only the '## Behaviour Fixes: <type>' block for that type, leaving all
     other sections — including Shared Behaviour and other type sections — untouched.
"""
from __future__ import annotations

import re
from typing import List

from llm.base import LLMMessage, with_retry
from llm.router import get_provider
from refinement.evaluator import CriterionScore

_VALID_TYPES = {"booking", "modification", "inquiry"}

# Section headers as they appear in the prompt (case-sensitive)
_SECTION_HEADERS = {
    "booking": "## Booking",
    "modification": "## Modification",
    "inquiry": "## Inquiry",
}

# Per-type fix block header, e.g. "## Behaviour Fixes: booking"
_FIX_HEADER_PREFIX = "## Behaviour Fixes: "


def _fix_section_re(conversation_type: str) -> re.Pattern:
    header = re.escape(f"{_FIX_HEADER_PREFIX}{conversation_type}")
    # Stop at the next '## Behaviour Fixes:' block or end of string so other
    # types' fix blocks are not consumed.
    return re.compile(r"\n+" + header + r".*?(?=\n+## Behaviour Fixes:|\Z)", re.DOTALL)


_LEGACY_FIX_RE = re.compile(
    r"\n+## Behaviour Fixes(?!:).*?(?=\n+## Behaviour Fixes:|\Z)",
    re.DOTALL,
)


def _strip_fix_block(prompt: str, conversation_type: str) -> str:
    """Remove the typed fix block for this type and any legacy untyped fix blocks.
    Other types' typed fix blocks are preserved."""
    cleaned = _LEGACY_FIX_RE.sub("", prompt)
    return _fix_section_re(conversation_type).sub("", cleaned).rstrip()


def _extract_section(prompt: str, conversation_type: str) -> str:
    """
    Return the content of the matching ## Section block so the fixer LLM
    has focused context without seeing irrelevant sections.
    """
    header = _SECTION_HEADERS.get(conversation_type, "")
    if not header:
        return ""

    # Find the section and collect lines until the next ## header or end of string
    lines = prompt.splitlines()
    in_section = False
    collected: List[str] = []
    for line in lines:
        if line.strip() == header:
            in_section = True
            collected.append(line)
            continue
        if in_section:
            if line.startswith("## ") and line.strip() != header:
                break
            collected.append(line)
    return "\n".join(collected).strip()


_FIXER_SYSTEM = """\
You are an expert prompt engineer for an AI airline customer service agent.

The system prompt is divided into sections: Shared Behaviour, Booking, Modification, and Inquiry.
You are only responsible for fixing the {section_header} section.
Do NOT change the Shared Behaviour section or any other section — those are off-limits.

Your task: given the current {section_header} section and a list of failures observed in a
{conversation_type} conversation, write a SHORT set of additional behavioural instructions
that fix those failures within the scope of {conversation_type} conversations.

Rules:
1. Output ONLY the new instructions — 2 to 6 bullet points, each starting with "- "
2. Each bullet must be a concrete, actionable rule the agent can follow
3. Do not repeat instructions already in the section shown to you
4. Do not output explanations, headings, preamble, markdown fences, or anything other
   than the bullet points themselves
5. Keep the total output under 400 characters
6. Focus only on {conversation_type} behaviour — do not introduce rules that affect other flows
"""

_FIXER_USER = """\
CURRENT {section_header} SECTION:
{section_content}

FAILURES TO FIX:
{failure_descriptions}

Write 2-6 bullet-point instructions (starting with '- ') that tell the agent exactly what \
to do differently in {conversation_type} conversations. Output ONLY the bullet points.
"""


def rewrite_prompt(
    current_prompt: str,
    failures: List[CriterionScore],
    conversation_type: str = "booking",
) -> str:
    """
    Patch the system prompt by appending a targeted fix block for conversation_type.

    Only the '## Behaviour Fixes: <conversation_type>' block is replaced.
    All other sections, including other types' fix blocks, are untouched.

    Returns current_prompt unchanged if no valid fix block is produced.
    """
    if not failures:
        return current_prompt

    if conversation_type not in _VALID_TYPES:
        conversation_type = "booking"

    base_prompt = _strip_fix_block(current_prompt, conversation_type)
    section_header = _SECTION_HEADERS.get(conversation_type, f"## {conversation_type.capitalize()}")
    section_content = _extract_section(base_prompt, conversation_type) or "(section not found)"

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

    system_content = _FIXER_SYSTEM.format(
        section_header=section_header,
        conversation_type=conversation_type,
    )
    user_content = _FIXER_USER.format(
        section_header=section_header,
        section_content=section_content,
        failure_descriptions=failure_descriptions,
        conversation_type=conversation_type,
    )

    fixer_llm = get_provider("prompt_fixer")
    messages = [
        LLMMessage.system(system_content),
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

    if not fix_block:
        return current_prompt

    if not any(line.strip().startswith("- ") for line in fix_block.splitlines()):
        _dbg("PROMPT FIXER REJECTED — no bullet points found", fix_block)
        return current_prompt

    if len(fix_block) > len(base_prompt) * 0.5:
        _dbg("PROMPT FIXER REJECTED — output suspiciously long (possible full rewrite)", fix_block[:200])
        return current_prompt

    forbidden = ["FAILURE:", "ROOT CAUSE:", "SCORE:", "```"]
    if any(token in fix_block for token in forbidden):
        _dbg("PROMPT FIXER REJECTED — forbidden tokens found", fix_block[:200])
        return current_prompt

    fix_header = f"{_FIX_HEADER_PREFIX}{conversation_type}"
    new_prompt = f"{base_prompt}\n\n{fix_header}\n{fix_block}"
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
