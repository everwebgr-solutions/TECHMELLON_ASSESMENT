"""Ollama local LLM provider — default for all tasks."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Type

import httpx
from pydantic import BaseModel

from config import OLLAMA_BASE_URL
from llm.base import LLMProvider, LLMProviderError


def _schema_instructions(schema: Type[BaseModel]) -> str:
    """Return a compact JSON schema description to insert into the system prompt."""
    return (
        f"\nRespond ONLY with a valid JSON object matching this schema:\n"
        f"{json.dumps(schema.model_json_schema(), indent=2)}\n"
        f"Do not include any explanation, markdown, or text outside the JSON."
    )


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
