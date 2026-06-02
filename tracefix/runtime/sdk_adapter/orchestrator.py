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
    SERVER_NAME, build_agent_mcp_server, allowed_tool_names, flag_only_send_schemas,
)
from tracefix.runtime.sdk_adapter.sdk_runner import run_sdk_agent
from tracefix.runtime.sdk_adapter.types import AgentResult
from tracefix.runtime.coordination.client import CoordClient

_DEFAULT_BUILTINS = ["Read", "Write", "Edit"]

_COORD_FOOTER = """

---
## Coordination tools (provided by the tracefix runtime)

You have these coordination tools in addition to your work tools:
acquire_lock(lock_id), release_lock(lock_id), send_message(channel_id, label),
receive_message(channel_id), poll_channels(channel_ids), receive_any(channel_ids),
signal_done(). Call signal_done() only when you have completed every protocol step.

Control plane vs data plane: coordination channels carry ONLY a label (a signal
flag like "submit"/"revise"/"accept") — never data or content. To hand another
agent some data/feedback, write it to a file (the data plane) at a path both
sides agree on, then send the label to signal it; the receiver reads the file.
Shared resources (locks) already protect shared documents/data — put content
there, not in messages.

Tool-call note: do NOT pass an `agent_id` argument to any tool — your identity is
already bound by the runtime. Pass only the arguments listed for each tool.
"""


@dataclass
class SdkRunResult:
    success: bool
    agent_results: list[AgentResult]
    duration: float
    error: str | None = None
    # Monitoring conclusions (otherwise the monitor runs but leaves no record):
    state_violations: list = field(default_factory=list)  # StateTracker soft violations
    premature_dones: list = field(default_factory=list)   # agents that signal_done'd early
    corrections_exceeded: list = field(default_factory=list)  # agents that hit the correction cap


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
        coord_url: str | None = None,
        live: bool = False,
        live_port: int = 8765,
        live_warmup: float = 4.0,
        live_hold: float = 0.0,
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
        # When set, each agent talks to a remote CoordinationService via a
        # CoordClient instead of sharing one in-process CoordinationContext.
        self.coord_url = coord_url
        # Real-time D3/SSE visualization (in-process mode only — see run()).
        self.live = live
        self.live_port = live_port
        self.live_warmup = live_warmup  # delay before agents start, so the browser connects first
        self.live_hold = live_hold      # keep the view up this long AFTER the run (inspection)
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
        """Domain tools, in priority order:
        1. a workspace-local ``tools.json`` (custom task — schema-only registry);
        2. the benchmark sim + tools for ``task_id``;
        3. ``None`` — the SDK builtins (Read/Write/Edit/Bash) ARE the domain layer.
        """
        ws_tools = self.workspace / "tools.json"
        if ws_tools.exists():
            try:
                from benchmark.tools import ToolRegistry
                if self.verbose:
                    print(f"[sdk] using workspace tools.json: {ws_tools}")
                return ToolRegistry.from_file(ws_tools)  # schema-only (no sim)
            except Exception as exc:  # noqa: BLE001
                if self.verbose:
                    print(f"[sdk] failed to load workspace tools.json: {exc}")
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

        # Live visualization (in-process mode only — in distributed mode the
        # coordination events live in the CoordinationService, not here).
        event_bus = None
        live_server = None
        if self.live and not self.coord_url:
            from tracefix.runtime.monitoring.event_bus import EventBus
            from tracefix.runtime.monitoring.live_server import start_live_server
            event_bus = EventBus()
            live_server = await start_live_server(
                ir, event_bus, port=self.live_port,
                title=f"Task {self.task_id} | SDK | {self.model or 'default'}",
                model=self.model or "")
            url = f"http://127.0.0.1:{self.live_port}"
            print(f"[sdk] Live view: {url}  (opening browser; agents start in "
                  f"{self.live_warmup:.0f}s)")
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception:  # noqa: BLE001 — headless is fine, the URL is printed
                pass
            # Warmup: let the browser open + connect to the SSE stream BEFORE the
            # agents act, so the whole run is visible (no missed early events).
            if self.live_warmup > 0:
                await asyncio.sleep(self.live_warmup)

        # Coordination backend. Distributed mode (coord_url set): each agent gets
        # its own CoordClient to a remote CoordinationService, where the monitor +
        # tracker live. In-process mode (default): one shared CoordinationContext.
        tracker = None
        coord = None
        if not self.coord_url:
            monitor = ProtocolMonitor(ir)
            states_path = self.workspace / "states.json"
            if states_path.exists():
                tracker = StateTracker(_load_json(states_path))
            coord = CoordinationContext(ir, monitor, tracker=tracker, correction=True,
                                        event_bus=event_bus)

        tool_registry = self._load_domain_tools()

        # Build a dispatcher + per-agent MCP server for every agent.
        runners = []
        for agent in ir["agents"]:
            agent_id = agent["id"]
            prompt = self._read_prompt(agent_id)

            domain_schemas = (
                tool_registry.openai_schemas(agent_id) if tool_registry else []
            )
            schemas = (flag_only_send_schemas(list(COORD_TOOL_SCHEMAS))
                       + list(domain_schemas))

            agent_coord = (CoordClient(self.coord_url, agent_id)
                           if self.coord_url else coord)
            dispatcher = CoordToolDispatcher(
                agent_coord, agent_id, tool_registry=tool_registry,
                event_bus=event_bus, verbose=self.verbose)
            mcp_server = build_agent_mcp_server(dispatcher, schemas)
            allowed = allowed_tool_names(schemas, SERVER_NAME) + list(self.builtins)

            runners.append((agent_id, dispatcher, run_sdk_agent(
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
        tasks = {asyncio.create_task(coro): (aid, disp) for aid, disp, coro in runners}
        done, pending = await asyncio.wait(
            tasks.keys(), timeout=timeout, return_when=asyncio.ALL_COMPLETED)

        results: list[AgentResult] = []
        for task in done:
            aid, disp = tasks[task]
            try:
                results.append(task.result())
            except Exception as e:  # noqa: BLE001 — keep the partial trace
                results.append(AgentResult(
                    agent_id=aid, steps=len(disp.trace), status="error",
                    error=str(e), trace=disp.trace))
        for task in pending:
            task.cancel()
            aid, disp = tasks[task]
            results.append(AgentResult(
                agent_id=aid, steps=len(disp.trace), status="timeout",
                error=f"exceeded global timeout {timeout}s", trace=disp.trace))

        duration = time.time() - start
        success = bool(results) and all(r.status == "completed" for r in results)

        # Surface the monitoring conclusions. ProtocolMonitor violations already
        # surface as tool errors in the agent traces; the StateTracker is the
        # monitor's *record* of protocol-conformance, which would otherwise be
        # discarded when the run ends.
        state_violations = []
        if self.coord_url:
            # Distributed: the tracker lives in the service — fetch its record.
            try:
                mon = await CoordClient(self.coord_url, "_orchestrator").fetch_monitoring()
                state_violations = mon.get("state_violations", [])
            except Exception:  # noqa: BLE001 — monitoring is best-effort
                pass
        elif tracker is not None:
            for v in tracker.violations:
                state_violations.append({
                    "agent": getattr(v, "agent", None),
                    "state": getattr(v, "current_state", None),
                    "operation": getattr(v, "operation", None),
                    "args": getattr(v, "args", None),
                })
        # premature_dones is client-side (the dispatcher's lock check) — always available.
        premature_dones = [aid for (aid, disp) in tasks.values()
                           if getattr(disp, "premature_done", False)]
        corrections_exceeded = [aid for (aid, disp) in tasks.values()
                                if getattr(disp, "correction_limit_exceeded", False)]

        result = SdkRunResult(
            success=success, agent_results=results, duration=duration,
            state_violations=state_violations, premature_dones=premature_dones,
            corrections_exceeded=corrections_exceeded)

        # Live viz: emit the terminal event, then shut the server down (the
        # browser keeps its rendered final state — the D3 view is client-side).
        if event_bus:
            await event_bus.emit("run.done", {
                "success": result.success,
                "duration": result.duration,
                "error": result.error,
                "protocol": {
                    "violations": state_violations,
                    "final_states": tracker.current_states if tracker else {},
                },
            })
            await asyncio.sleep(1.0)  # let a connected browser receive final events
            if self.live_hold > 0:
                print(f"[sdk] holding live view at http://127.0.0.1:{self.live_port} "
                      f"for {self.live_hold:.0f}s — inspect the final state now")
                await asyncio.sleep(self.live_hold)
            await event_bus.close()
        if live_server:
            from tracefix.runtime.monitoring.live_server import stop_live_server
            await stop_live_server(live_server)

        return result
