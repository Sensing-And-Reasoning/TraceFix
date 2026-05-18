"""Unified multi-provider LLM client (standalone, no v1 dependency).

Supports OpenAI and Anthropic providers via lazy imports.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""
    provider: str  # "openai", "anthropic", or "openrouter"
    model: str
    api_key: str
    temperature: float = 1.0
    max_tokens: int = 32768
    # OpenAI reasoning: "low"/"medium"/"high" (gpt-5/gpt-5-mini/gpt-5-nano/o3/o4-mini)
    reasoning_effort: str = "high"
    # Anthropic extended thinking: >0 enables thinking with this token budget
    thinking_budget: int = 0
    # Custom API base URL (e.g. OpenRouter: "https://openrouter.ai/api/v1")
    base_url: str = ""

    @property
    def model_key(self) -> str:
        return self.model

    @property
    def has_reasoning(self) -> bool:
        """Whether this config enables API-level reasoning."""
        return bool(self.reasoning_effort) or self.thinking_budget > 0


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    content: str
    model: str
    usage: dict = field(default_factory=dict)
    raw_response: Any = None
    latency_seconds: float = 0.0


class LLMClient:
    """Unified LLM client dispatching to OpenAI or Anthropic."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._openai_client = None
        self._anthropic_client = None

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[dict] = None,
    ) -> LLMResponse:
        if self.config.provider in ("openai", "openrouter"):
            return self._chat_openai(system_prompt, user_prompt, response_format)
        elif self.config.provider == "anthropic":
            return self._chat_anthropic(system_prompt, user_prompt)
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

    def _chat_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[dict] = None,
    ) -> LLMResponse:
        from openai import OpenAI

        if self._openai_client is None:
            client_kwargs: dict[str, Any] = {"api_key": self.config.api_key}
            if self.config.base_url:
                client_kwargs["base_url"] = self.config.base_url
            self._openai_client = OpenAI(**client_kwargs)
        client = self._openai_client

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        # OpenRouter / third-party endpoints use max_tokens; native OpenAI uses max_completion_tokens
        if self.config.base_url:
            kwargs["max_tokens"] = self.config.max_tokens
        else:
            kwargs["max_completion_tokens"] = self.config.max_tokens
        if self.config.reasoning_effort:
            # Reasoning models (gpt-5/gpt-5-mini/gpt-5-nano/o3/o4-mini):
            # use reasoning_effort, DO NOT pass temperature (forbidden by API)
            kwargs["reasoning_effort"] = self.config.reasoning_effort
        else:
            # Non-reasoning models: use temperature
            if self.config.temperature != 1.0:
                kwargs["temperature"] = self.config.temperature
        if response_format is not None:
            kwargs["response_format"] = response_format

        # Retry on OpenAI's non-deterministic invalid_prompt content filter
        max_retries = 5
        start = time.time()
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(**kwargs)
                break
            except Exception as e:
                if "invalid_prompt" in str(e) and attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(
                        f"  [Retry {attempt+1}/{max_retries}] invalid_prompt filter hit, "
                        f"waiting {wait}s...",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
                    continue
                raise
        latency = time.time() - start

        choice = response.choices[0]
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage=usage,
            raw_response=response,
            latency_seconds=latency,
        )

    def _chat_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMResponse:
        from anthropic import Anthropic

        if self._anthropic_client is None:
            self._anthropic_client = Anthropic(api_key=self.config.api_key)
        client = self._anthropic_client

        api_kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        if self.config.thinking_budget > 0:
            # Extended thinking: temperature must be 1.0
            api_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.config.thinking_budget,
            }
            api_kwargs["temperature"] = 1.0
        else:
            api_kwargs["temperature"] = self.config.temperature

        start = time.time()
        response = client.messages.create(**api_kwargs)
        latency = time.time() - start

        # Extract only text blocks (skip thinking blocks)
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

        return LLMResponse(
            content=content,
            model=response.model,
            usage=usage,
            raw_response=response,
            latency_seconds=latency,
        )
