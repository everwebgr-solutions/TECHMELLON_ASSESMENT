"""LLM provider interface and shared types."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel


class LLMMessage(dict):
    """A message dict with role and content."""

    @classmethod
    def system(cls, content: str) -> "LLMMessage":
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> "LLMMessage":
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str) -> "LLMMessage":
        return cls(role="assistant", content=content)


class LLMProviderError(Exception):
    pass


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    def complete(
        self,
        messages: List[Dict[str, str]],
        response_schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.7,
    ) -> Any:
        """
        Complete a conversation.
        If response_schema is given, return a validated instance of that model.
        Otherwise, return the raw string response.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider/model name."""


def with_retry(
    fn,
    *args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    **kwargs,
) -> Any:
    """
    Retry fn(*args, **kwargs) up to max_attempts times.
    On structured output parse failure the error is appended to the message list.
    On network errors exponential backoff is applied.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except (LLMProviderError, ValueError) as exc:
            last_exc = exc
            if attempt < max_attempts:
                time.sleep(base_delay * (2 ** (attempt - 1)))
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                time.sleep(base_delay * (2 ** (attempt - 1)))

    raise LLMProviderError(
        f"All {max_attempts} attempts failed. Last error: {last_exc}"
    ) from last_exc
