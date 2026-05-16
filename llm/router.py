"""
LLM router — maps task names to provider instances via config.
Supports hot-swapping providers by changing environment variables.
"""
from __future__ import annotations

from typing import Dict

from config import (
    LLM_CODE_PATCHER,
    LLM_EVALUATOR,
    LLM_PROMPT_FIXER,
    LLM_SIMULATOR,
)
from llm.base import LLMProvider

_TASK_CONFIG: Dict[str, str] = {
    "simulator": LLM_SIMULATOR,
    "evaluator": LLM_EVALUATOR,
    "prompt_fixer": LLM_PROMPT_FIXER,
    "code_patcher": LLM_CODE_PATCHER,
}


def _build_provider(spec: str) -> LLMProvider:
    """
    Parse 'provider/model' spec and instantiate the correct provider.
    Examples: 'ollama/llama3.2', 'openai/gpt-4o', 'anthropic/claude-haiku-4-5-20251001'
    """
    if "/" not in spec:
        raise ValueError(f"Invalid provider spec '{spec}'. Expected 'provider/model'.")

    provider_name, model = spec.split("/", 1)

    if provider_name == "ollama":
        from llm.ollama_provider import OllamaProvider
        return OllamaProvider(model=model)

    if provider_name == "openai":
        from llm.openai_provider import OpenAIProvider
        return OpenAIProvider(model=model)

    if provider_name == "anthropic":
        from llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(model=model)

    raise ValueError(f"Unknown LLM provider '{provider_name}'")


def get_provider(task: str) -> LLMProvider:
    """Return the configured provider for a given task name."""
    spec = _TASK_CONFIG.get(task)
    if spec is None:
        raise ValueError(
            f"Unknown task '{task}'. Valid tasks: {list(_TASK_CONFIG.keys())}"
        )
    return _build_provider(spec)
