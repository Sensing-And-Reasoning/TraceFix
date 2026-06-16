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
import secrets
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from tracefix.runtime.monitoring.coord import CoordinationContext
from tracefix.runtime.monitoring.monitor import ProtocolMonitor
from tracefix.runtime.monitoring.state_tracker import StateTracker
from tracefix.runtime.coordination.service import CoordinationService
from tracefix.runtime.coordination.client import CoordClient
from tracefix.runtime.workspace_layout import (
    spec_path, snapshot_run_workspace, new_run_stamp, shared_workdir, agent_workdir)
from tracefix.runtime.opencode_adapter.config_gen import agent_key, build_agent_config, domain_wiring
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

Optional telemetry: `tracefix_report_progress(label)` — announce a finer business
sub-phase you are working on (e.g. "reading_research", "generating_figure"). It is
NEVER required, never affects success, and can never be out of order. Use it sparingly
to make your progress visible; it does not replace any coordination step.

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
    current_phases: dict = field(default_factory=dict)  # agent → business phase
    beacons: list = field(default_factory=list)          # report_progress beacons


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
        coord_url: str | None = None,
        agents: list[str] | None = None,
        output_dir: Path | str | None = None,
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
        # Distributed/mixed mode: connect to an EXTERNAL CoordinationService instead
        # of starting one — the authoritative monitor+tracker+correction live there.
        self.coord_url = coord_url
        # Run only this subset of the IR's agents (mixed/partial run); None = all.
        self.agents = agents
        # Write to this exact output dir (shared across a mixed run) instead of
        # creating a per-run snapshot; None = own snapshot.
        self.output_override = Path(output_dir) if output_dir is not None else None
        self.snapshot_dir: Path | None = None  # set per run() → <workspace>-<stamp>/
        self.run_dir: Path | None = None        # = snapshot_dir/output (agents' cwd)

    # -- workspace / prompt helpers -----------------------------------------

    def _prompts_dir(self) -> Path:
        d = self.workspace / "prompts" / "runtime_b"
        return d if d.is_dir() else self.workspace / "prompts"

    def _read_prompt(self, agent_id: str) -> str:
        path = self._prompts_dir() / f"{agent_id}.md"
        return path.read_text() + _COORD_FOOTER + self._output_footer(agent_id)

    def _output_footer(self, agent_id: str) -> str:
        shared = shared_workdir(self.run_dir).resolve()
        private = agent_workdir(self.run_dir, agent_id).resolve()
        return (
            f"\n\n## Where to write files\n"
            f"Your working directory is the SHARED area:\n`{shared}`\n"
            f"When your steps name a file another agent reads (a handoff), read/write "
            f"it here — a plain relative filename works (it resolves to this dir). All "
            f"agents share it; the locks in your protocol protect shared files.\n"
            f"For files only YOU use (scratch, your own test files, intermediate work), "
            f"write under your PRIVATE directory:\n`{private}`\n"
            f"Keep private files out of the shared area so peers aren't affected.\n")

    # -- run -----------------------------------------------------------------

    async def run(self) -> OpencodeRunResult:
        ir = _load_json(spec_path(self.workspace, "ir.json"))
        # Output dir: a shared override (mixed/distributed run writes alongside
        # another harness) or this run's OWN timestamped snapshot workspace
        # `<workspace>-<stamp>/` (inputs + verified spec/ + prompts/ copied, fresh
        # output/) — a self-contained, traceable record of which spec produced
        # which artifacts; `<workspace>-latest` → it. Agents' cwd is output/.
        if self.output_override is not None:
            self.run_dir = self.output_override
            self.run_dir.mkdir(parents=True, exist_ok=True)
            self.snapshot_dir = self.run_dir.parent
        else:
            self.snapshot_dir = snapshot_run_workspace(self.workspace, new_run_stamp())
            self.run_dir = self.snapshot_dir / "output"

        # Optional real-time D3/SSE visualization. The CoordinationContext emits
        # state.transition / state.violation as the service processes each RPC, so
        # the protocol view updates live; agent tool calls are layered on from the
        # OpenCode JSONL streams.
        event_bus = None
        live_server = None
        if self.live and not self.coord_url:  # distributed: events live in the service
            from tracefix.runtime.monitoring.event_bus import EventBus
            from tracefix.runtime.monitoring.live_server import start_live_server
            event_bus = EventBus()
            live_server = await start_live_server(
                ir, event_bus, port=self.live_port,
                title=f"Task {self.task_id} | OpenCode",  # model now shown in the summary panel
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

        # Coordination: connect to an EXTERNAL service (mixed/distributed) or start
        # our OWN in-process one (standalone). The monitor+tracker+correction are
        # authoritative wherever the service runs.
        tokens: dict[str, str] | None = None
        if self.coord_url:
            coord_url = self.coord_url
            service = None
            tracker = None  # lives in the external service
        else:
            monitor = ProtocolMonitor(ir)
            states_path = spec_path(self.workspace, "states.json")
            tracker = StateTracker(_load_json(states_path)) if states_path.exists() else None
            coord = CoordinationContext(ir, monitor, tracker=tracker, correction=True,
                                        event_bus=event_bus)
            # Per-agent capability tokens: opencode agents have Bash and the coord URL,
            # so without this one agent could curl the loopback port and forge ops as a
            # peer. Each agent gets its own token (via its MCP server env); the service
            # binds agent_id→token and rejects mismatches.
            tokens = {a["id"]: secrets.token_hex(16) for a in ir["agents"]}
            service = CoordinationService(coord, host=self.host, port=self.port,
                                          verbose=self.verbose, tokens=tokens)
            await service.start()
            coord_url = f"http://{self.host}:{self.port}"
        coord_cmd = [sys.executable, "-m", "tracefix.runtime.coord_mcp"]
        domain_cmd = [sys.executable, "-m", "tracefix.runtime.domain_mcp"]
        out = str(self.run_dir.resolve())          # run-output root (holds .agents/ XDG)
        shared_out = str(shared_workdir(self.run_dir).resolve())  # agents' cwd (--dir)
        run_agents = [a for a in ir["agents"]
                      if self.agents is None or a["id"] in self.agents]
        print(f"[opencode] run snapshot → {self.snapshot_dir}", file=sys.stderr)
        if self.verbose:
            print(f"[opencode] coord={coord_url} | "
                  f"agents={[a['id'] for a in run_agents]} | output={out}",
                  file=sys.stderr)

        start = time.time()

        # Live trace: emit the SAME event shape the live view consumes (it was built
        # for the monitoring runtime — agent_runner.py). opencode fires a tool_use
        # event per state (pending/running/completed); emit one trace row per call,
        # on the terminal state, with a per-agent round counter and elapsed-since-start.
        tool_rounds: dict[str, int] = {}
        # Last cumulative (input, output) tokens seen per agent — opencode reports a
        # running total on each step_finish, so we emit the DELTA (the live view adds
        # llm_end token counts) to avoid double-counting.
        tok_seen: dict[str, tuple] = {}

        def _on_event(agent_id: str, ev: dict) -> None:
            if event_bus is None:
                return
            etype = ev.get("type")
            # Agent "thinking" pulse + token meter: opencode emits step-start when a
            # model turn begins and step-finish (with cumulative tokens) when it ends.
            if etype == "step_start":
                asyncio.create_task(event_bus.emit("agent.llm_start", {"agent_id": agent_id}))
                return
            if etype == "step_finish":
                part = ev.get("part") or {}
                toks = part.get("tokens") or {}
                cur_in = int(toks.get("input", 0) or 0)
                cur_out = int(toks.get("output", 0) or 0)
                prev_in, prev_out = tok_seen.get(agent_id, (0, 0))
                tok_seen[agent_id] = (cur_in, cur_out)
                asyncio.create_task(event_bus.emit("agent.llm_end", {
                    "agent_id": agent_id,
                    # tokens are cumulative per message → emit the per-step delta
                    "input_tokens": max(0, cur_in - prev_in),
                    "output_tokens": max(0, cur_out - prev_out),
                    # cost is opencode's own per-step figure → emit as-is (JS sums it)
                    "cost": float(part.get("cost") or 0),
                }))
                return
            if etype != "tool_use":
                return
            st = (ev.get("part") or {}).get("state") or {}
            status = st.get("status")
            if status not in ("completed", "error"):
                return  # ignore pending/running — one row per finished call
            tool_rounds[agent_id] = tool_rounds.get(agent_id, 0) + 1
            payload = st.get("output") if status == "completed" else st.get("error")
            # Coordination tools return a JSON result ({"status":"acquired"/"sent"/
            # "received"/"released", ...}). Surface THAT as `result` so the live view's
            # lock-holder, beam, and channel-count logic (which keys off
            # result.status === "acquired"/"received"/…) fires — otherwise opencode's
            # tool-execution "completed" masks the coordination outcome and locks read
            # "free" forever. Builtins return plain text → wrap it.
            result = {"status": status, "output": payload}
            if isinstance(payload, str):
                try:
                    parsed = json.loads(payload)
                    if isinstance(parsed, dict) and "status" in parsed:
                        result = parsed
                except (ValueError, TypeError):
                    pass
            # opencode namespaces MCP tools `<server>_<tool>`; strip the `tracefix_`
            # prefix so coordination tools match the live view's names (acquire_lock,
            # send_message, ...) and drive its beam / lock-holder / channel-count
            # animations, exactly as the monitoring runtime does.
            tool = (ev.get("part") or {}).get("tool") or ""
            if tool.startswith("tracefix_"):
                tool = tool[len("tracefix_"):]
            asyncio.create_task(event_bus.emit("agent.tool_call", {
                "agent_id": agent_id,
                "round": tool_rounds[agent_id],
                "tool_name": tool,
                "arguments": st.get("input") or {},
                "result": result,
                "elapsed": time.time() - start,
            }))

        on_event = _on_event if event_bus is not None else None

        # Start the run clock on the client: the live view bases its elapsed timer on
        # the run.start `_ts`. The browser has connected during the warmup above, and
        # the server does not replay history, so emit it here (just before agents run).
        if event_bus is not None:
            await event_bus.emit("run.start", {"agents": [a["id"] for a in run_agents]})
        try:
            tasks = []
            inst_root = Path(out) / ".agents"
            for idx, agent in enumerate(run_agents):
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
                    coord_cmd=coord_cmd,
                    token=tokens.get(agent_id) if tokens else None,
                    domain=domain_wiring(self.workspace, agent_id, domain_cmd=domain_cmd))
                # Pre-create this agent's private dir; cwd (--dir) is the shared area.
                agent_workdir(self.run_dir, agent_id)

                # Wrap so the live view turns each agent node green/red the moment IT
                # finishes (agent.done), instead of leaving every node idle until the
                # whole run ends.
                async def _run_agent(aid=agent_id, cfg=cfg, xdg_env=xdg_env):
                    t0 = time.time()  # this agent's own wall-clock (it may start staggered)
                    try:
                        res = await run_opencode_agent(
                            aid, cfg, opencode_cmd=self.opencode_cmd,
                            output_dir=shared_out, timeout=self.timeout,
                            on_event=on_event, env_overrides=xdg_env)
                    except BaseException as e:  # noqa: BLE001
                        if event_bus is not None:
                            await event_bus.emit("agent.done", {
                                "agent_id": aid, "status": "error",
                                "duration": time.time() - t0,
                                "error": f"{type(e).__name__}: {e}"})
                        raise
                    if event_bus is not None:
                        await event_bus.emit("agent.done", {
                            "agent_id": aid, "status": res.get("status", "completed"),
                            "duration": time.time() - t0,
                            "error": res.get("error")})
                    return res

                tasks.append(asyncio.create_task(_run_agent()))

            raw = await asyncio.gather(*tasks, return_exceptions=True)
            duration = time.time() - start

            agent_results: list[dict] = []
            for agent, res in zip(run_agents, raw):
                aid = agent["id"]
                if isinstance(res, BaseException):
                    agent_results.append({"agent_id": aid, "status": "error",
                                          "error": f"{type(res).__name__}: {res}"})
                else:
                    agent_results.append(res)

            success = bool(agent_results) and all(
                r.get("status") == "completed" for r in agent_results)

            state_violations, current_states = [], {}
            current_phases: dict = {}
            beacons: list = []
            if self.coord_url:
                # tracker lives in the external service — fetch its record.
                try:
                    mon = await CoordClient(self.coord_url,
                                            "_orchestrator").fetch_monitoring()
                    state_violations = mon.get("state_violations", [])
                    current_states = mon.get("current_states", {})
                    current_phases = mon.get("current_phases", {})
                    beacons = mon.get("beacons", [])
                except Exception:  # noqa: BLE001 — monitoring is best-effort
                    pass
            elif tracker is not None:
                for v in tracker.violations:
                    state_violations.append({
                        "agent": getattr(v, "agent", None),
                        "state": getattr(v, "current_state", None),
                        "operation": getattr(v, "operation", None),
                        "args": getattr(v, "args", None)})
                current_states = dict(tracker.current_states)
                current_phases = dict(tracker.current_phases)
                beacons = list(getattr(coord, "beacons", []))
            premature_dones = [r["agent_id"] for r in agent_results
                               if r.get("premature_done")]
            corrections_exceeded = [r["agent_id"] for r in agent_results
                                    if r.get("correction_limit")]

            result = OpencodeRunResult(
                success=success, agent_results=agent_results, duration=duration,
                state_violations=state_violations, current_states=current_states,
                premature_dones=premature_dones,
                corrections_exceeded=corrections_exceeded,
                run_dir=str(self.snapshot_dir),
                current_phases=current_phases, beacons=beacons)

            if event_bus is not None:
                await event_bus.emit("run.done", {
                    "success": result.success, "duration": result.duration,
                    "error": result.error,
                    "protocol": {"violations": state_violations,
                                 "final_states": current_states,
                                 "phases": current_phases,
                                 "beacons": beacons}})
                await asyncio.sleep(1.0)
                if self.live_hold > 0:
                    print(f"[opencode] holding live view at "
                          f"http://127.0.0.1:{self.live_port} for "
                          f"{self.live_hold:.0f}s — inspect the final state now")
                    await asyncio.sleep(self.live_hold)
                await event_bus.close()
            return result
        finally:
            if service is not None:
                await service.stop()
            if live_server is not None:
                from tracefix.runtime.monitoring.live_server import stop_live_server
                await stop_live_server(live_server)
