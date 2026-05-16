"""Anthropic (Claude) provider — optional quality upgrade."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

from config import ANTHROPIC_API_KEY
from llm.base import LLMProvider, LLMProviderError


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        if not ANTHROPIC_API_KEY:
            raise LLMProviderError("ANTHROPIC_API_KEY is not set")
        self._model = model
        import anthropic
        self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    @property
    def name(self) -> str:
        return f"anthropic/{self._model}"

    def complete(
        self,
        messages: List[Dict[str, str]],
        response_schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.7,
    ) -> Any:
        # Anthropic separates system from conversation messages
        system_content = ""
        conversation: List[Dict[str, str]] = []
        for msg in messages:
            if msg["role"] == "system":
                system_content += msg["content"] + "\n"
            else:
                conversation.append(msg)

        if response_schema is not None:
            schema_str = json.dumps(response_schema.model_json_schema(), indent=2)
            system_content += (
                f"\nRespond ONLY with a valid JSON object matching this schema:\n{schema_str}\n"
                f"Do not include any explanation or text outside the JSON object."
            )

        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system_content.strip() or "You are a helpful assistant.",
                messages=conversation,
                temperature=temperature,
            )
            content = resp.content[0].text
        except Exception as exc:
            raise LLMProviderError(f"Anthropic request failed: {exc}") from exc

        if response_schema is not None:
            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if json_match:
                content = json_match.group(1)
            else:
                # Try to find raw JSON object
                obj_match = re.search(r"\{.*\}", content, re.DOTALL)
                if obj_match:
                    content = obj_match.group(0)
            try:
                return response_schema.model_validate_json(content)
            except Exception as exc:
                raise ValueError(
                    f"Structured output parse failed for {response_schema.__name__}: {exc}\n"
                    f"Raw: {content[:500]}"
                ) from exc

        return content
