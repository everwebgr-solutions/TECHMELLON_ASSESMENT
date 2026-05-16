"""Ollama local LLM provider — default for all tasks."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Type

import httpx
from pydantic import BaseModel

from config import OLLAMA_BASE_URL
from llm.base import LLMProvider, LLMProviderError


def _schema_instructions(schema: Type[BaseModel]) -> str:
    """
    Return structured output instructions based on an example instance.
    Uses an example rather than raw JSON Schema to avoid confusing smaller models.
    """
    # Build a flat, example-driven description of the expected output
    try:
        example = _build_example(schema)
        example_json = json.dumps(example, indent=2)
    except Exception:
        # Fallback: strip $defs complexity from schema
        raw = schema.model_json_schema()
        raw.pop("$defs", None)
        example_json = json.dumps(raw, indent=2)

    return (
        f"\nRespond ONLY with a valid JSON object. Do not include markdown, code fences, or any text outside the JSON.\n"
        f"Expected output format (fill in real values, do not copy this example verbatim):\n"
        f"{example_json}\n"
    )


def _build_example(schema: Type[BaseModel]) -> Dict[str, Any]:
    """Build a concrete filled example for well-known schemas."""
    from refinement.evaluator import EvaluationResult  # local import to avoid circular
    if schema is EvaluationResult:
        return {
            "scenario_id": "book_next_available",
            "understanding": {
                "score": 7,
                "failure_quotes": ["Agent asked for destination twice without searching"],
                "root_cause": "prompt",
                "root_cause_detail": "Agent repeatedly asked for the destination instead of calling search_flights. This is an instruction-following failure."
            },
            "api_correctness": {
                "score": 4,
                "failure_quotes": ["I'm sorry, I wasn't able to complete your booking due to a system error"],
                "root_cause": "code",
                "root_cause_detail": "FILE: api/routes/webhooks.py::webhook_book_flight\nThe book_flight webhook returned an error despite being called with valid parameters. The agent correctly attempted the booking but the backend rejected it."
            },
            "outcome_confirmation": {
                "score": 6,
                "failure_quotes": ["Booking reference was never provided to the customer"],
                "root_cause": "prompt",
                "root_cause_detail": "Agent ended the call without reading out the booking reference. The system prompt requires confirming the reference number clearly."
            },
            "naturalness": {
                "score": 8,
                "failure_quotes": [],
                "root_cause": "none",
                "root_cause_detail": ""
            },
            "overall_pass": False,
            "summary": "Agent understood the request but the booking failed due to a backend error, and the agent did not confirm the reference."
        }
    # Generic fallback
    return {"error": "unknown schema"}


class OllamaProvider(LLMProvider):
    def __init__(self, model: str, base_url: str = OLLAMA_BASE_URL):
        self._model = model
        self._base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:
        return f"ollama/{self._model}"

    def complete(
        self,
        messages: List[Dict[str, str]],
        response_schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.7,
    ) -> Any:
        msgs = list(messages)

        if response_schema is not None:
            # Inject schema instructions into the last system message or prepend one
            instructions = _schema_instructions(response_schema)
            if msgs and msgs[0]["role"] == "system":
                msgs[0] = {**msgs[0], "content": msgs[0]["content"] + instructions}
            else:
                msgs.insert(0, {"role": "system", "content": instructions})

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": msgs,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if response_schema is not None:
            payload["format"] = "json"

        try:
            resp = httpx.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=120.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Ollama request failed: {exc}") from exc

        content: str = resp.json()["message"]["content"]

        if response_schema is not None:
            try:
                return response_schema.model_validate_json(content)
            except Exception as exc:
                raise ValueError(
                    f"Structured output parse failed for {response_schema.__name__}: {exc}\n"
                    f"Raw response: {content[:500]}"
                ) from exc

        return content
