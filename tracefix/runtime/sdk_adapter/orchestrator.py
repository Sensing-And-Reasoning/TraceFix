"""Orchestrator: run a tracefix workspace with Claude-Agent-SDK agents.

Mirrors ``tracefix.runtime.monitoring.orchestrator`` but swaps the per-agent
loop for the Claude Agent SDK. The coordination layer
(``CoordinationContext`` + ``ProtocolMonitor`` + ``StateTracker`` + stores) is
reused **unchanged** — this file only changes who drives the agents.

Setup sequence (per ``run()``):
  1. load ir.json (+ optional states.json)
  2. ProtocolMonitor(ir)  →  StateTracker(states)  →  CoordinationContext(...)
  3. auto-discover benchmark sim + domain tools (optional; same as monitoring)
  4. per agent: read prompts/runtime_b/<id>.md, build dispatcher + MCP server
  5. asyncio.gather the SDK runners under a global timeout
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from tracefix.runtime.monitoring.coord import CoordinationContext, COORD_TOOL_SCHEMAS
from tracefix.runtime.monitoring.monitor import ProtocolMonitor
from tracefix.runtime.monitoring.state_tracker import StateTracker

from tracefix.runtime.sdk_adapter.dispatch import CoordToolDispatcher
from tracefix.runtime.sdk_adapter.mcp_server import (
    SERVER_NAME, build_agent_mcp_server, allowed_tool_names,
)
from tracefix.runtime.sdk_adapter.sdk_runner import run_sdk_agent
from tracefix.runtime.sdk_adapter.types import AgentResult

_DEFAULT_BUILTINS = ["Read", "Write", "Edit"]

_COORD_FOOTER = """

---
## Coordination tools (provided by the tracefix runtime)

You have these coordination tools in addition to your work tools:
acquire_lock(lock_id), release_lock(lock_id), send_message(channel_id, label, body?),
receive_message(channel_id), poll_channels(channel_ids), receive_any(channel_ids),
signal_done(). Call signal_done() only when you have completed every protocol step.
"""


@dataclass
class SdkRunResult:
    success: bool
    agent_results: list[AgentResult]
    duration: float
    error: str | None = None


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


class SdkOrchestrator:
    """Loads a verified workspace and runs its agents via the Claude Agent SDK."""

    def __init__(
        self,
        task_id: str,
        workspace: Path | str,
        *,
        model: str | None = None,
        builtins: list[str] | None = None,
        max_rounds: int = 50,
        verbose: bool = False,
        scenario: int | None = None,
        difficulty: int = 1,
        tool_time: float | None = None,
        seed: int | None = None,
    ):
        self.task_id = task_id
        self.workspace = Path(workspace)
        self.model = model
        self.builtins = _DEFAULT_BUILTINS if builtins is None else builtins
        self.max_rounds = max_rounds
        self.verbose = verbose
        self.scenario = scenario
        self.difficulty = difficulty
        self.tool_time = tool_time
        self.seed = seed
        self.sim = None

    # -- workspace helpers ---------------------------------------------------

    def _prompts_dir(self) -> Path:
        d = self.workspace / "prompts" / "runtime_b"
        if d.is_dir():
            return d
        return self.workspace / "prompts"

    def _read_prompt(self, agent_id: str) -> str:
        path = self._prompts_dir() / f"{agent_id}.md"
        return path.read_text() + _COORD_FOOTER

    def _load_domain_tools(self):
        """Auto-discover the benchmark sim + tools (best-effort, same as monitoring)."""
        try:
            import importlib
            from benchmark.tools import load_tools, ToolConfig

            fast_cfg = ToolConfig(min_delay=0.0, max_delay=0.0, fail_probability=0.0)
            try:
                sim_mod = importlib.import_module(
                    f"benchmark.environments.{self.task_id}.sim")
                for attr in dir(sim_mod):
                    obj = getattr(sim_mod, attr)
                    if (isinstance(obj, type) and attr.endswith("Sim")
                            and obj.__module__ == sim_mod.__name__):
                        self.sim = obj()
                        break
                if self.sim is not None:
                    if self.tool_time is not None:
                        self.sim._delay_multiplier = self.tool_time
                    if self.seed is not None:
                        self.sim._seed = self.seed
                    if self.scenario is not None:
                        self.sim.set_scenario_depth(self.scenario)
                    else:
                        self.sim.set_difficulty(self.difficulty)
            except (ModuleNotFoundError, ImportError):
                pass

            return load_tools(self.task_id, config=fast_cfg, sim=self.sim)
        except Exception as exc:  # noqa: BLE001
            if self.verbose:
                print(f"[sdk] no benchmark tools for {self.task_id}: {exc}")
            return None

    # -- run -----------------------------------------------------------------

    async def run(self, timeout: float = 180.0) -> SdkRunResult:
        ir = _load_json(self.workspace / "ir.json")

        monitor = ProtocolMonitor(ir)

        tracker = None
        states_path = self.workspace / "states.json"
        if states_path.exists():
            tracker = StateTracker(_load_json(states_path))

        coord = CoordinationContext(ir, monitor, tracker=tracker)

        tool_registry = self._load_domain_tools()

        # Build a dispatcher + per-agent MCP server for every agent.
        runners = []
        for agent in ir["agents"]:
            agent_id = agent["id"]
            prompt = self._read_prompt(agent_id)

            domain_schemas = (
                tool_registry.openai_schemas(agent_id) if tool_registry else []
            )
            schemas = list(COORD_TOOL_SCHEMAS) + list(domain_schemas)

            dispatcher = CoordToolDispatcher(
                coord, agent_id, tool_registry=tool_registry, verbose=self.verbose)
            mcp_server = build_agent_mcp_server(dispatcher, schemas)
            allowed = allowed_tool_names(schemas, SERVER_NAME) + list(self.builtins)

            runners.append((agent_id, run_sdk_agent(
                agent_id=agent_id,
                system_prompt=prompt,
                dispatcher=dispatcher,
                mcp_server=mcp_server,
                allowed_tools=allowed,
                server_name=SERVER_NAME,
                model=self.model,
                max_rounds=self.max_rounds,
                verbose=self.verbose,
            )))

        start = time.time()
        tasks = {asyncio.create_task(coro): aid for aid, coro in runners}
        done, pending = await asyncio.wait(
            tasks.keys(), timeout=timeout, return_when=asyncio.ALL_COMPLETED)

        results: list[AgentResult] = []
        for task in done:
            try:
                results.append(task.result())
            except Exception as e:  # noqa: BLE001
                results.append(AgentResult(
                    agent_id=tasks[task], steps=0, status="error", error=str(e)))
        for task in pending:
            task.cancel()
            results.append(AgentResult(
                agent_id=tasks[task], steps=0, status="timeout",
                error=f"exceeded global timeout {timeout}s"))

        duration = time.time() - start
        success = bool(results) and all(r.status == "completed" for r in results)
        return SdkRunResult(success=success, agent_results=results, duration=duration)
