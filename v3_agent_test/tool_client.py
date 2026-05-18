"""Provider-agnostic LLM client with tool calling support.

Abstracts OpenAI and Anthropic tool-calling APIs behind a unified interface.
Uses lazy imports — only the selected provider's SDK is loaded.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from v3_agent_test.pipeline.llm_client import LLMConfig


@dataclass
class ToolCall:
    """A tool call requested by the LLM.

    `id` is the provider-specific call identifier. For Chat Completions it is
    `choice.message.tool_calls[*].id`; for Responses API it is the `call_id`
    field on a `function_call` output block.
    """

    id: str
    name: str
    arguments: dict


def _needs_responses_api(config: LLMConfig) -> bool:
    """Return True when the (provider, model) combination requires /v1/responses.

    As of April 2026, gpt-5.4 (and its mini/nano/pro variants) reject function
    tools + reasoning_effort on /v1/chat/completions with a 400 telling the
    caller to use /v1/responses. gpt-5 / gpt-5-mini / gpt-5-nano still work on
    Chat Completions, so we keep them on the legacy path to avoid regressions.
    """
    if config.provider != "openai":
        return False
    model = (config.model or "").lower()
    if model.startswith("gpt-5.4"):
        return True
    return False


@dataclass
class AgentResponse:
    """Unified response from the LLM."""

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    raw_response: Any = None


class ToolClient:
    """LLM client that supports tool calling for both OpenAI and Anthropic.

    Messages use a canonical format that gets translated to provider-specific
    format at the API boundary:

    Canonical message types:
      {"role": "system", "content": "..."}
      {"role": "user", "content": "..."}
      {"role": "assistant", "content": "...", "tool_calls": [...]}  # optional tool_calls
      {"role": "tool_result", "tool_call_id": "...", "content": "..."}
    """

    def __init__(self, config: LLMConfig, tool_schemas: list[dict]):
        """Initialize with LLM config and tool definitions.

        Args:
            config: LLMConfig with provider, model, api_key, etc.
            tool_schemas: List of tool schemas in canonical format:
                {"name": str, "description": str, "parameters": dict}
        """
        self.config = config
        self.tool_schemas = tool_schemas
        self._openai_client = None
        self._anthropic_client = None

    def chat(self, messages: list[dict]) -> AgentResponse:
        """Send messages with tool definitions, get back text or tool calls."""
        if self.config.provider == "openai":
            # gpt-5.4 and future GPT-5.x releases require the Responses API
            # (/v1/responses) when tools + reasoning_effort are combined — Chat
            # Completions returns 400 "Function tools with reasoning_effort are
            # not supported for gpt-5.4". OpenRouter still goes through Chat
            # Completions because the Responses API is not proxied there.
            if _needs_responses_api(self.config):
                return self._chat_openai_responses(messages)
            return self._chat_openai(messages)
        elif self.config.provider == "openrouter":
            return self._chat_openai(messages)
        elif self.config.provider == "anthropic":
            return self._chat_anthropic(messages)
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

    # ------------------------------------------------------------------
    # OpenAI implementation
    # ------------------------------------------------------------------

    def _chat_openai(self, messages: list[dict]) -> AgentResponse:
        from openai import OpenAI

        if self._openai_client is None:
            client_kwargs: dict[str, Any] = {"api_key": self.config.api_key, "max_retries": 3}
            if self.config.base_url:
                client_kwargs["base_url"] = self.config.base_url
            self._openai_client = OpenAI(**client_kwargs)

        # Convert canonical messages to OpenAI format
        oai_messages = self._to_openai_messages(messages)

        # Convert tool schemas to OpenAI format
        oai_tools = [
            {
                "type": "function",
                "function": {
                    "name": s["name"],
                    "description": s["description"],
                    "parameters": s["parameters"],
                },
            }
            for s in self.tool_schemas
        ]

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": oai_messages,
            "tools": oai_tools,
        }
        # OpenRouter / third-party endpoints use max_tokens; native OpenAI uses max_completion_tokens
        if self.config.base_url:
            kwargs["max_tokens"] = self.config.max_tokens
        else:
            kwargs["max_completion_tokens"] = self.config.max_tokens

        # Reasoning models: use reasoning_effort, no temperature
        if self.config.reasoning_effort:
            kwargs["reasoning_effort"] = self.config.reasoning_effort
        else:
            if self.config.temperature != 1.0:
                kwargs["temperature"] = self.config.temperature

        # Retry on OpenAI's non-deterministic invalid_prompt content filter
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = self._openai_client.chat.completions.create(**kwargs)
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

        choice = response.choices[0]

        # Parse text content
        text = choice.message.content

        # Parse tool calls
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        usage = {}
        if response.usage:
            cached = 0
            details = getattr(response.usage, "prompt_tokens_details", None)
            if details:
                cached = getattr(details, "cached_tokens", 0) or 0
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "cached_tokens": cached,
            }

        return AgentResponse(
            text=text,
            tool_calls=tool_calls,
            usage=usage,
            raw_response=response,
        )

    def _to_openai_messages(self, messages: list[dict]) -> list[dict]:
        """Convert canonical messages to OpenAI format."""
        result = []
        for msg in messages:
            role = msg["role"]

            if role == "system":
                result.append({"role": "system", "content": msg["content"]})

            elif role == "user":
                result.append({"role": "user", "content": msg["content"]})

            elif role == "assistant":
                oai_msg: dict[str, Any] = {"role": "assistant"}
                if msg.get("content"):
                    oai_msg["content"] = msg["content"]
                if msg.get("tool_calls"):
                    oai_msg["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"]),
                            },
                        }
                        for tc in msg["tool_calls"]
                    ]
                result.append(oai_msg)

            elif role == "tool_result":
                result.append({
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "content": msg["content"],
                })

        return result

    # ------------------------------------------------------------------
    # OpenAI Responses API (/v1/responses) — required for gpt-5.4 when tools
    # are attached. Differs from Chat Completions in four places:
    #   1. Input uses "input" instead of "messages"; assistant messages with
    #      tool calls split into a text message block + separate
    #      `function_call` items; tool results are `function_call_output`
    #      items (not role="tool" messages).
    #   2. Tool schemas are flat (`type: "function"` at top level, no inner
    #      `function: {...}` wrapper).
    #   3. `reasoning_effort` becomes `reasoning={"effort": "..."}` and
    #      `max_completion_tokens` becomes `max_output_tokens`.
    #   4. Output is a list of typed blocks (`reasoning` | `message` |
    #      `function_call`); each `function_call` carries a `call_id` that
    #      must be echoed back as `call_id` on the corresponding
    #      `function_call_output`.
    # ------------------------------------------------------------------

    def _chat_openai_responses(self, messages: list[dict]) -> AgentResponse:
        from openai import OpenAI

        if self._openai_client is None:
            client_kwargs: dict[str, Any] = {"api_key": self.config.api_key, "max_retries": 3}
            if self.config.base_url:
                client_kwargs["base_url"] = self.config.base_url
            self._openai_client = OpenAI(**client_kwargs)

        resp_input = self._to_responses_input(messages)

        # Responses API tools: flat schema (no inner "function" wrapper).
        resp_tools = [
            {
                "type": "function",
                "name": s["name"],
                "description": s["description"],
                "parameters": s["parameters"],
            }
            for s in self.tool_schemas
        ]

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "input": resp_input,
            "tools": resp_tools,
            "max_output_tokens": self.config.max_tokens,
            # Stateless: do NOT persist conversation server-side. We resend the
            # full canonical history each turn, matching the existing Chat
            # Completions contract.
            "store": False,
        }
        if self.config.reasoning_effort:
            kwargs["reasoning"] = {"effort": self.config.reasoning_effort}

        # Retry on OpenAI's non-deterministic invalid_prompt content filter
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = self._openai_client.responses.create(**kwargs)
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

        # Parse response.output blocks
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.output:
            btype = getattr(block, "type", None)
            if btype == "message":
                # content is a list of {"type": "output_text", "text": str} parts
                for part in getattr(block, "content", []) or []:
                    ptype = getattr(part, "type", None)
                    if ptype in ("output_text", "text"):
                        text = getattr(part, "text", "") or ""
                        if text:
                            text_parts.append(text)
            elif btype == "function_call":
                raw_args = getattr(block, "arguments", "") or ""
                try:
                    args = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(
                    # call_id is what must be echoed back on function_call_output
                    id=getattr(block, "call_id", "") or getattr(block, "id", ""),
                    name=getattr(block, "name", ""),
                    arguments=args,
                ))
            # Ignore reasoning blocks — they carry private trace only, no
            # user-visible content to append.

        text = "\n".join(text_parts) if text_parts else None

        usage = {}
        if getattr(response, "usage", None):
            cached = 0
            details = getattr(response.usage, "input_tokens_details", None)
            if details is not None:
                cached = getattr(details, "cached_tokens", 0) or 0
            input_tokens = getattr(response.usage, "input_tokens", 0)
            output_tokens = getattr(response.usage, "output_tokens", 0)
            usage = {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cached_tokens": cached,
            }

        return AgentResponse(
            text=text,
            tool_calls=tool_calls,
            usage=usage,
            raw_response=response,
        )

    def _to_responses_input(self, messages: list[dict]) -> list[dict]:
        """Convert canonical messages to Responses API input items.

        Key transformations vs Chat Completions:
          - assistant message with tool_calls → one optional text message item
            plus one `function_call` item per tool call.
          - tool_result → `function_call_output` item with matching `call_id`.
        """
        result: list[dict] = []
        for msg in messages:
            role = msg["role"]

            if role in ("system", "user"):
                result.append({"role": role, "content": msg["content"]})

            elif role == "assistant":
                content = msg.get("content") or ""
                tool_calls = msg.get("tool_calls") or []
                # Emit the assistant's textual reply first (if any), then each
                # function_call as its own top-level item.
                if content:
                    result.append({"role": "assistant", "content": content})
                for tc in tool_calls:
                    result.append({
                        "type": "function_call",
                        "call_id": tc["id"],
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"]),
                    })

            elif role == "tool_result":
                result.append({
                    "type": "function_call_output",
                    "call_id": msg["tool_call_id"],
                    "output": msg["content"],
                })

        return result

    # ------------------------------------------------------------------
    # Anthropic implementation
    # ------------------------------------------------------------------

    def _chat_anthropic(self, messages: list[dict]) -> AgentResponse:
        from anthropic import Anthropic

        if self._anthropic_client is None:
            self._anthropic_client = Anthropic(api_key=self.config.api_key, max_retries=3)

        # Extract system message and convert to Anthropic format
        system_text, api_messages = self._to_anthropic_messages(messages)

        # Convert tool schemas to Anthropic format
        anth_tools = [
            {
                "name": s["name"],
                "description": s["description"],
                "input_schema": s["parameters"],
            }
            for s in self.tool_schemas
        ]

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": api_messages,
            "tools": anth_tools,
        }
        if system_text:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system_text,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        # Cache the last tool definition (covers all tools in the prefix)
        if anth_tools:
            anth_tools[-1]["cache_control"] = {"type": "ephemeral"}

        if self.config.thinking_budget > 0:
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.config.thinking_budget,
            }
            kwargs["temperature"] = 1.0
        else:
            kwargs["temperature"] = self.config.temperature

        response = self._anthropic_client.messages.create(**kwargs)

        # Parse content blocks
        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                ))

        text = "\n".join(text_parts) if text_parts else None

        cached = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            "cached_tokens": cached,
        }

        return AgentResponse(
            text=text,
            tool_calls=tool_calls,
            usage=usage,
            raw_response=response,
        )

    def _to_anthropic_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Convert canonical messages to Anthropic format.

        Returns (system_text, api_messages).
        Anthropic requires:
          - system as a separate parameter
          - tool results wrapped in user messages with tool_result content blocks
          - assistant tool calls as tool_use content blocks
        """
        system_text = ""
        result: list[dict] = []

        for msg in messages:
            role = msg["role"]

            if role == "system":
                system_text = msg["content"]

            elif role == "user":
                result.append({"role": "user", "content": msg["content"]})

            elif role == "assistant":
                content_blocks: list[dict] = []
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc["arguments"],
                        })
                if content_blocks:
                    result.append({"role": "assistant", "content": content_blocks})

            elif role == "tool_result":
                # Anthropic: tool results go in a user message
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": msg["tool_call_id"],
                    "content": msg["content"],
                }
                # Check if previous message is already a user message with tool_results
                # (batch multiple tool results into one user message)
                if (
                    result
                    and result[-1]["role"] == "user"
                    and isinstance(result[-1]["content"], list)
                    and result[-1]["content"]
                    and result[-1]["content"][0].get("type") == "tool_result"
                ):
                    result[-1]["content"].append(tool_result_block)
                else:
                    result.append({
                        "role": "user",
                        "content": [tool_result_block],
                    })

        return system_text, result
