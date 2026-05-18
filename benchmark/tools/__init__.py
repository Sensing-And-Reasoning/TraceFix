"""Benchmark tool registry for simulation-based task environments."""

from typing import Any

from ._base import ToolConfig, ToolResult
from ._registry import ToolRegistry


def load_tools(
    task_id: str,
    config: ToolConfig | None = None,
    sim: Any = None,
) -> ToolRegistry:
    """Load the tool registry for a benchmark task.

    Args:
        task_id: Task identifier (e.g., "3E", "12E").
        config: Optional ToolConfig to override default settings.
        sim: SimContext instance providing tool implementations.  Required.

    Returns:
        ToolRegistry with tool schemas and sim-backed implementations.
    """
    return ToolRegistry(task_id, config, sim=sim)


__all__ = ["load_tools", "ToolConfig", "ToolResult", "ToolRegistry"]
