"""Result/trace dataclasses for the SDK adapter.

Field-compatible with ``tracefix.runtime.monitoring.agent_runner.ToolCall`` and
``AgentResult`` so the same result-saver / visualizer can consume either — but
defined here so the SDK adapter does NOT import ``agent_runner`` (which pulls in
the OpenAI SDK). An SDK-driven runtime should not depend on the OpenAI client.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    round: int
    tool_name: str
    arguments: dict
    result: dict
    elapsed: float
    timestamp: float = 0.0


@dataclass
class AgentResult:
    agent_id: str
    steps: int
    status: str  # "completed" | "incomplete" | "error" | "timeout"
    duration: float = 0.0
    error: str | None = None
    trace: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
