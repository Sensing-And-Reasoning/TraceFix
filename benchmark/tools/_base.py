"""Shared primitives for benchmark tool infrastructure."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolConfig:
    """Runtime configuration for tool execution."""

    min_delay: float = 1.0
    max_delay: float = 5.0
    fail_probability: float = 0.3

    def __post_init__(self):
        if self.min_delay < 0 or self.max_delay < self.min_delay:
            raise ValueError("need 0 <= min_delay <= max_delay")
        if not 0 <= self.fail_probability <= 1:
            raise ValueError("fail_probability must be in [0, 1]")


@dataclass
class ToolResult:
    """Standard return type for all sim tool calls."""

    tool_name: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    delay_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "delay_seconds": round(self.delay_seconds, 3),
        }
