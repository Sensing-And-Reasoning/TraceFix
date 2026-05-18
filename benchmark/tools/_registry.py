"""Per-task tool loading and dispatch."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ._base import ToolConfig, ToolResult

_BASE_DIR = Path(__file__).parent.parent
_TASKS_DIR = _BASE_DIR / "descriptions"


class ToolRegistry:
    """Loads a task's tool schemas and dispatches calls to the simulation context.

    Args:
        task_id: Task identifier (e.g., "3E", "12E").
        config: Optional ToolConfig (used for registry metadata; sim controls actual delays/failures).
        sim: SimContext instance providing tool implementations.  Required.
    """

    def __init__(
        self,
        task_id: str,
        config: ToolConfig | None = None,
        sim: Any = None,
    ):
        if sim is None:
            raise ValueError(
                f"ToolRegistry requires a sim instance for task '{task_id}'. "
                "Pass sim=<SimContext> when calling load_tools()."
            )
        self.task_id = task_id
        self.config = config or ToolConfig()
        self._sim = sim
        self._schemas: list[dict[str, Any]] = []
        self._tool_agents: dict[str, list[str]] = {}
        self._tool_fns: dict[str, Any] = {}
        self._load()

    def _load(self):
        schema_path = _TASKS_DIR / self.task_id / "tools.json"
        if not schema_path.exists():
            raise FileNotFoundError(f"No schema file: {schema_path}")

        with open(schema_path) as f:
            raw_schemas = json.load(f)

        sim_tools: dict[str, Any] = self._sim.make_tools()

        for entry in raw_schemas:
            fn_def = entry.get("function", entry)
            tool_name = fn_def["name"]

            agent_ids = fn_def.pop("agent_ids", [])
            fn_def.pop("can_fail", None)
            self._tool_agents[tool_name] = agent_ids

            self._schemas.append(entry)

            if tool_name not in sim_tools:
                raise KeyError(
                    f"Sim for task '{self.task_id}' does not implement tool '{tool_name}'. "
                    f"Available: {', '.join(sim_tools) or '(none)'}"
                )
            self._tool_fns[tool_name] = sim_tools[tool_name]

    @property
    def tool_names(self) -> list[str]:
        return list(self._tool_fns.keys())

    def tools_for_agent(self, agent_id: str) -> list[str]:
        """Return tool names available to a specific agent."""
        return [
            name
            for name, agents in self._tool_agents.items()
            if not agents or agent_id in agents
        ]

    def openai_schemas(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        """Return OpenAI function-calling format schemas, optionally filtered by agent."""
        result = []
        for schema in self._schemas:
            fn_def = schema.get("function", schema)
            tool_name = fn_def["name"]
            if agent_id and self._tool_agents.get(tool_name):
                if agent_id not in self._tool_agents[tool_name]:
                    continue
            clean = json.loads(json.dumps(schema))
            clean_fn = clean.get("function", clean)
            clean_fn.pop("agent_ids", None)
            clean_fn.pop("can_fail", None)
            result.append(clean)
        return result

    async def call(
        self,
        tool_name: str,
        agent_id: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute a tool via the simulation context.

        Args:
            tool_name: Name of the tool to call.
            agent_id: Required — passed to the sim for resource tracking and failure injection.
            **kwargs: Tool-specific parameters.
        """
        if tool_name not in self._tool_fns:
            raise KeyError(f"Unknown tool '{tool_name}' for task {self.task_id}")
        if agent_id is None:
            raise ValueError("agent_id is required")

        fn = self._tool_fns[tool_name]
        resources = self._sim.resource_requirements(tool_name, agent_id=agent_id, **kwargs)
        if resources:
            self._sim.begin_resource_use(agent_id, tool_name, resources)
        try:
            lo, hi = self._sim.tool_delay(tool_name, **kwargs)
            m = self._sim._delay_multiplier
            rng = self._sim._rng_for(agent_id)
            delay = rng.uniform(lo * m, hi * m) if hi > 0 and m > 0 else 0.0
            result = fn(agent_id, **kwargs)
            result.delay_seconds = delay
            if delay > 0:
                await asyncio.sleep(delay)
            return result
        finally:
            if resources:
                self._sim.end_resource_use(agent_id, resources)
