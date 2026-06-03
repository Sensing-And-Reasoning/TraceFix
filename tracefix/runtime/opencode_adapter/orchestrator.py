"""Orchestrator: run a tracefix workspace with OpenCode as the per-agent harness.

Mirrors ``sdk_adapter.orchestrator.SdkOrchestrator`` but each agent is an
independent OpenCode *process* (a peer) instead of an in-process SDK loop. Since
those processes are separate, the coordination state can't be shared in-process:
the orchestrator starts ONE in-process ``CoordinationService`` (the verified
``CoordinationContext`` + monitor + tracker + correction), and every agent's
OpenCode process spawns a per-agent ``tracefix-coord`` stdio MCP server that
talks back to it over HTTP. The coordination core is reused **unchanged**.

Setup sequence (per ``run()``):
  1. load ir.json (+ optional states.json) via spec_path
  2. ProtocolMonitor -> StateTracker -> CoordinationContext(correction=True)
  3. start a CoordinationService on host:port (serves /rpc + /monitoring)
  4. per agent: assemble the runtime prompt, generate OPENCODE_CONFIG_CONTENT,
     drive ``opencode run`` as a subprocess (config_gen + driver)
  5. asyncio.gather the drivers (each self-terminates at its own wall-clock cap)
  6. read the monitor's conclusions off the in-process tracker; stop the service
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from tracefix.runtime.monitoring.coord import CoordinationContext
from tracefix.runtime.monitoring.monitor import ProtocolMonitor
from tracefix.runtime.monitoring.state_tracker import StateTracker
from tracefix.runtime.coordination.service import CoordinationService
from tracefix.runtime.workspace_layout import spec_path, snapshot_run_workspace, new_run_stamp
from tracefix.runtime.opencode_adapter.config_gen import agent_key, build_agent_config
from tracefix.runtime.opencode_adapter.driver import run_opencode_agent

# OpenCode namespaces MCP tools ``<mcpServer>_<tool>``; our mcp server key is "tracefix".
_COORD_FOOTER = """

---
## Coordination tools (tracefix runtime)

Your coordination tools are exposed with a `tracefix_` prefix:
`tracefix_acquire_lock(lock_id)`, `tracefix_release_lock(lock_id)`,
`tracefix_send_message(channel_id, label)`, `tracefix_receive_message(channel_id)`,
`tracefix_poll_channels(channel_ids)`, `tracefix_receive_any(channel_ids)`,
`tracefix_signal_done()`.

When your protocol steps name a coordination tool WITHOUT the prefix (e.g.
`acquire_lock`), call the prefixed tool (`tracefix_acquire_lock`). Call
`tracefix_signal_done()` only after you have completed every protocol step.

Control plane vs data plane: coordination channels carry ONLY a label (a signal
flag like "ready"/"submit") — never data or content. To hand another agent data,
write it to a file in your working directory and send the label to signal it.
Do NOT pass an `agent_id` argument to any coordination tool — your identity is
already bound by the runtime.
"""


@dataclass
class OpencodeRunResult:
    success: bool
    agent_results: list           # one driver disposition dict per agent
    duration: float
    error: str | None = None
    state_violations: list = field(default_factory=list)
    current_states: dict = field(default_factory=dict)
    premature_dones: list = field(default_factory=list)
    corrections_exceeded: list = field(default_factory=list)
    run_dir: str = ""


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


class OpencodeOrchestrator:
    """Loads a verified workspace and runs its agents as OpenCode processes."""

    def __init__(
        self,
        task_id: str,
        workspace: Path | str,
        *,
        model: str | None = None,
        opencode_cmd: list[str] | None = None,
        host: str = "127.0.0.1",
        port: int = 8780,
        op_timeout_ms: int = 120_000,
        timeout: float = 600.0,
        start_stagger: float = 10.0,
        verbose: bool = False,
        live: bool = False,
        live_port: int = 8765,
        live_warmup: float = 4.0,
        live_hold: float = 0.0,
    ):
        self.task_id = task_id
        self.workspace = Path(workspace)
        self.model = model
        self.opencode_cmd = list(opencode_cmd) if opencode_cmd else ["opencode"]
        self.host = host
        self.port = port
        self.op_timeout_ms = op_timeout_ms
        self.timeout = timeout
        self.start_stagger = start_stagger
        self.verbose = verbose
        self.live = live
        self.live_port = live_port
        self.live_warmup = live_warmup
        self.live_hold = live_hold
        self.snapshot_dir: Path | None = None  # set per run() → <workspace>-<stamp>/
        self.run_dir: Path | None = None        # = snapshot_dir/output (agents' cwd)

    # -- workspace / prompt helpers -----------------------------------------

    def _prompts_dir(self) -> Path:
        d = self.workspace / "prompts" / "runtime_b"
        return d if d.is_dir() else self.workspace / "prompts"

    def _read_prompt(self, agent_id: str) -> str:
        path = self._prompts_dir() / f"{agent_id}.md"
        return path.read_text() + _COORD_FOOTER + self._output_footer()

    def _output_footer(self) -> str:
        out = self.run_dir.resolve()
        return (
            f"\n\n## Where to write files (shared data plane)\n"
            f"Your working directory is the shared output directory:\n`{out}`\n"
            f"When your instructions mention a file by name (e.g. `research.md`, "
            f"`data_check.md`, `ACCEPTANCE.md`), read and write it there — a plain "
            f"relative filename works (it resolves to this directory). All agents "
            f"share this directory; the locks in your protocol protect shared files. "
            f"Do NOT write files anywhere else.\n")

    # -- run -----------------------------------------------------------------

    async def run(self) -> OpencodeRunResult:
        ir = _load_json(spec_path(self.workspace, "ir.json"))
        # Snapshot this run to a timestamped sibling workspace
        # `<workspace>-<stamp>/` (inputs + verified spec/ + prompts/ copied from
        # the base, fresh output/), so every run is a self-contained, traceable
        # record of which verified spec produced which artifacts.
        # `<workspace>-latest` → newest run. Agents' cwd is its output/ subdir.
        self.snapshot_dir = snapshot_run_workspace(self.workspace, new_run_stamp())
        self.run_dir = self.snapshot_dir / "output"

        # Optional real-time D3/SSE visualization. The CoordinationContext emits
        # state.transition / state.violation as the service processes each RPC, so
        # the protocol view updates live; agent tool calls are layered on from the
        # OpenCode JSONL streams.
        event_bus = None
        live_server = None
        if self.live:
            from tracefix.runtime.monitoring.event_bus import EventBus
            from tracefix.runtime.monitoring.live_server import start_live_server
            event_bus = EventBus()
            live_server = await start_live_server(
                ir, event_bus, port=self.live_port,
                title=f"Task {self.task_id} | OpenCode | {self.model or 'default'}",
                model=self.model or "")
            url = f"http://127.0.0.1:{self.live_port}"
            print(f"[opencode] Live view: {url}  (opening browser; agents start in "
                  f"{self.live_warmup:.0f}s)")
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception:  # noqa: BLE001
                pass
            if self.live_warmup > 0:
                await asyncio.sleep(self.live_warmup)

        monitor = ProtocolMonitor(ir)
        states_path = spec_path(self.workspace, "states.json")
        tracker = StateTracker(_load_json(states_path)) if states_path.exists() else None
        coord = CoordinationContext(ir, monitor, tracker=tracker, correction=True,
                                    event_bus=event_bus)
        service = CoordinationService(coord, host=self.host, port=self.port,
                                      verbose=self.verbose)
        await service.start()
        coord_url = f"http://{self.host}:{self.port}"
        coord_cmd = [sys.executable, "-m", "tracefix.runtime.coord_mcp"]
        out = str(self.run_dir.resolve())
        print(f"[opencode] run snapshot → {self.snapshot_dir}", file=sys.stderr)
        if self.verbose:
            print(f"[opencode] CoordinationService on {coord_url} | "
                  f"agents={len(ir['agents'])} | output={out}", file=sys.stderr)

        def _on_event(agent_id: str, ev: dict) -> None:
            if event_bus is None or ev.get("type") != "tool_use":
                return
            part = ev.get("part") or {}
            asyncio.create_task(event_bus.emit("agent.tool_call", {
                "agent_id": agent_id,
                "tool": part.get("tool"),
                "status": (part.get("state") or {}).get("status"),
            }))

        on_event = _on_event if event_bus is not None else None

        start = time.time()
        try:
            tasks = []
            inst_root = Path(out) / ".agents"
            for idx, agent in enumerate(ir["agents"]):
                agent_id = agent["id"]
                # Stagger spawns so OpenCode's per-instance cold-start + one-time DB
                # migration don't storm simultaneously. Peers may start at different
                # times — the FIFO channels queue messages, so a late receiver still
                # gets them and the protocol's locks still serialize correctly.
                if idx > 0 and self.start_stagger > 0:
                    await asyncio.sleep(self.start_stagger)
                # OpenCode roots all durable state in machine-global XDG dirs: a
                # GLOBAL state flock (xdgState/opencode/locks) + a per-XDG-data SQLite
                # DB. Processes sharing the default XDG dirs serialize on that flock
                # and contend on the WAL DB. Give each agent its OWN XDG_DATA_HOME
                # (per-agent DB → no cross-process WAL contention) and XDG_STATE_HOME
                # (per-agent Flock root → no cross-process lock contention).
                #
                # Deliberately DO NOT isolate XDG_CACHE: opencode caches the ripgrep
                # binary under XDG_CACHE/opencode/bin, so a fresh per-agent cache makes
                # every agent re-download ripgrep from GitHub (verified: 20+ min hang).
                # Sharing the default *warm* cache → ~4.5s cold start. XDG_CONFIG is
                # unused — the per-agent config arrives via OPENCODE_CONFIG_CONTENT.
                # Agents still SHARE the working dir (`out`) for data-plane files.
                inst = inst_root / agent_key(agent_id)
                for sub in ("data", "state"):
                    (inst / sub).mkdir(parents=True, exist_ok=True)
                xdg_env = {
                    "XDG_DATA_HOME": str(inst / "data"),
                    "XDG_STATE_HOME": str(inst / "state"),
                }
                cfg = build_agent_config(
                    agent_id, coord_url, prompt=self._read_prompt(agent_id),
                    model=self.model, op_timeout_ms=self.op_timeout_ms,
                    coord_cmd=coord_cmd)
                tasks.append(asyncio.create_task(run_opencode_agent(
                    agent_id, cfg, opencode_cmd=self.opencode_cmd,
                    output_dir=out, timeout=self.timeout, on_event=on_event,
                    env_overrides=xdg_env)))

            raw = await asyncio.gather(*tasks, return_exceptions=True)
            duration = time.time() - start

            agent_results: list[dict] = []
            for agent, res in zip(ir["agents"], raw):
                aid = agent["id"]
                if isinstance(res, BaseException):
                    agent_results.append({"agent_id": aid, "status": "error",
                                          "error": f"{type(res).__name__}: {res}"})
                else:
                    agent_results.append(res)

            success = bool(agent_results) and all(
                r.get("status") == "completed" for r in agent_results)

            state_violations, current_states = [], {}
            if tracker is not None:
                for v in tracker.violations:
                    state_violations.append({
                        "agent": getattr(v, "agent", None),
                        "state": getattr(v, "current_state", None),
                        "operation": getattr(v, "operation", None),
                        "args": getattr(v, "args", None)})
                current_states = dict(tracker.current_states)
            premature_dones = [r["agent_id"] for r in agent_results
                               if r.get("premature_done")]
            corrections_exceeded = [r["agent_id"] for r in agent_results
                                    if r.get("correction_limit")]

            result = OpencodeRunResult(
                success=success, agent_results=agent_results, duration=duration,
                state_violations=state_violations, current_states=current_states,
                premature_dones=premature_dones,
                corrections_exceeded=corrections_exceeded,
                run_dir=str(self.snapshot_dir))

            if event_bus is not None:
                await event_bus.emit("run.done", {
                    "success": result.success, "duration": result.duration,
                    "error": result.error,
                    "protocol": {"violations": state_violations,
                                 "final_states": current_states}})
                await asyncio.sleep(1.0)
                if self.live_hold > 0:
                    print(f"[opencode] holding live view at "
                          f"http://127.0.0.1:{self.live_port} for "
                          f"{self.live_hold:.0f}s — inspect the final state now")
                    await asyncio.sleep(self.live_hold)
                await event_bus.close()
            return result
        finally:
            await service.stop()
            if live_server is not None:
                from tracefix.runtime.monitoring.live_server import stop_live_server
                await stop_live_server(live_server)
