"""OpenAI provider — optional quality upgrade over local Ollama."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

from config import OPENAI_API_KEY
from llm.base import LLMProvider, LLMProviderError


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str = "gpt-4o-mini"):
        if not OPENAI_API_KEY:
            raise LLMProviderError("OPENAI_API_KEY is not set")
        self._model = model
        # Lazy import — openai may not be installed
        import openai
        self._client = openai.OpenAI(api_key=OPENAI_API_KEY)

    @property
    def name(self) -> str:
        return f"openai/{self._model}"

    def complete(
        self,
        messages: List[Dict[str, str]],
        response_schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.7,
    ) -> Any:
        try:
            if response_schema is not None:
                resp = self._client.beta.chat.completions.parse(
                    model=self._model,
                    messages=messages,
                    response_format=response_schema,
                    temperature=temperature,
                )
                return resp.choices[0].message.parsed
            else:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=temperature,
                )
                return resp.choices[0].message.content
        except Exception as exc:
            raise LLMProviderError(f"OpenAI request failed: {exc}") from exc
