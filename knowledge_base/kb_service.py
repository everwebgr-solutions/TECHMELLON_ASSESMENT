"""
Knowledge base service — loads policies.json once at import and serves sections by key.
Deterministic lookup; no fuzzy matching, no embeddings.
"""
from __future__ import annotations

import json
from pathlib import Path

_POLICIES_PATH = Path(__file__).parent / "policies.json"

with _POLICIES_PATH.open() as _f:
    _POLICIES: dict = json.load(_f)

VALID_TOPICS = list(_POLICIES.keys())


def get(topic: str) -> dict | None:
    """Return the policy section for *topic*, or None if unknown."""
    return _POLICIES.get(topic)


def get_all() -> dict:
    """Return the full policy document."""
    return _POLICIES


def list_topics() -> list[str]:
    """Return all available policy topic keys."""
    return VALID_TOPICS


def search(query: str) -> dict:
    """
    Naive keyword search across all topics.
    Returns a dict of {topic: section} for any section whose text contains the query term.
    Intended as a fallback when the agent does not know the exact topic key.
    """
    query_lower = query.lower()
    results = {}
    for topic, section in _POLICIES.items():
        if query_lower in json.dumps(section).lower():
            results[topic] = section
    return results
