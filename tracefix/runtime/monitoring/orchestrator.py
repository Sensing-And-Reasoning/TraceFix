"""RuntimeB orchestrator: loads config, creates agents, runs them concurrently.

Reads from workspace/:
  - ir.json           → Monitor whitelist + CoordinationContext stores
  - prompts/{agent}.md → pre-generated per-agent system prompts
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from tracefix.runtime.monitoring.monitor import ProtocolMonitor
from tracefix.runtime.monitoring.coord import CoordinationContext, COORD_TOOL_SCHEMAS
from tracefix.runtime.workspace_layout import spec_path
from tracefix.runtime.monitoring.agent_runner import AgentRunner, AgentConfig, AgentResult
from tracefix.runtime.monitoring.state_tracker import StateTracker


@dataclass
class RunResult:
    success: bool
    agent_results: list[AgentResult]
    duration: float
    error: str | None = None
    state_violations: list = field(default_factory=list)
    corrections_exceeded: list = field(default_factory=list)  # agents that hit the correction cap


_ROOT = Path(__file__).resolve().parent.parent

# Appended to every agent prompt with coordination tool usage rules
_COORD_FOOTER = """

## Coordination Tool Behavior

### acquire_lock(lock_id)
Waits internally for up to 30 seconds until the lock is available. Returns:
- `{"status": "acquired"}` — you now hold the lock, proceed with your work
- `{"status": "timeout"}` — lock still held by another agent after 30s, retry
- `{"status": "already_held"}` — you already hold this lock, no need to acquire again

### release_lock(lock_id)
Always succeeds immediately.

### send_message(channel_id, label)
Always succeeds immediately. Channels carry a finite **label only** — never free-form data. To share data with another agent, write it to a file (the data plane) and send the label as the "it's ready" signal.

### receive_message(channel_id)
Waits up to 30 seconds for a message. Returns:
- `{"status": "received", "label": "..."}` — message arrived; the label is the signal (read any shared file it refers to)
- `{"status": "timeout"}` — no message within 30s, retry

### signal_done()
When you are DONE (reached your final step), call `signal_done()` to terminate.
You MUST call signal_done() — do NOT just stop calling tools.
"""


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


class RuntimeB:
    """Load workspace config, create agents, run them concurrently."""

    def __init__(
        self,
        task_id: str,
        workspace: Path | str,
        model: str = "gpt-5-mini",
        api_key: str = "",
        verbose: bool = False,
        live: bool = False,
        live_port: int = 8765,
        scenario: int | None = None,
        difficulty: int = 1,
        tool_time: float | None = None,
        seed: int | None = None,
        max_rounds: int = 50,
    ):
        self.task_id = task_id
        self.workspace = Path(workspace)
        self.model = model
        self.api_key = api_key
        self.verbose = verbose
        self.live = live
        self.live_port = live_port
        self.scenario = scenario
        self.difficulty = difficulty
        self.tool_time = tool_time
        self.seed = seed
        self.max_rounds = max_rounds

    async def run(self, timeout: float = 120.0) -> RunResult:
        t0 = time.monotonic()

        # 1. Load IR (topology only)
        ir = _load_json(spec_path(self.workspace, "ir.json"))

        # 2. Create Monitor + StateTracker
        monitor = ProtocolMonitor(ir)
        tracker = None
        states_path = spec_path(self.workspace, "states.json")
        if states_path.exists():
            states_data = json.loads(states_path.read_text())
            tracker = StateTracker(states_data)
            if self.verbose:
                print(f"[RuntimeB] State tracker loaded: "
                      f"{len(states_data.get('states', []))} states")

        # 3. Live visualization setup
        event_bus = None
        live_server = None
        if self.live:
            from tracefix.runtime.monitoring.event_bus import EventBus
            from tracefix.runtime.monitoring.live_server import start_live_server
            event_bus = EventBus()
            title = f"Task {self.task_id} | {self.model}"
            live_server = await start_live_server(
                ir, event_bus, port=self.live_port, title=title,
                model=self.model)
            url = f"http://127.0.0.1:{self.live_port}"
            print(f"[RuntimeB] Live view: {url}")
            import webbrowser
            webbrowser.open(url)

        # 3b. Create CoordinationContext (after event_bus is available)
        coord = CoordinationContext(ir, monitor, tracker=tracker, event_bus=event_bus,
                                    correction=True)
        self._coord = coord

        # 4. Load domain tools (optional, with fast config for runtime)
        tool_registry = None
        self.sim = None
        try:
            from benchmark.tools import load_tools, ToolConfig
            import importlib as _imp

            fast_cfg = ToolConfig(min_delay=0.0, max_delay=0.0, fail_probability=0.0)

            # Auto-discover sim module for this task
            try:
                sim_mod = _imp.import_module(
                    f"benchmark.environments.{self.task_id}.sim")
                # Find the task-specific *Sim class (defined in this module)
                for attr in dir(sim_mod):
                    obj = getattr(sim_mod, attr)
                    if (isinstance(obj, type) and attr.endswith("Sim")
                            and obj.__module__ == sim_mod.__name__):
                        self.sim = obj()
                        break
                # Apply sim-layer configuration
                if self.sim is not None:
                    if self.tool_time is not None:
                        self.sim._delay_multiplier = self.tool_time
                    if self.seed is not None:
                        self.sim._seed = self.seed
                    # Failure injection (mutually exclusive)
                    # --scenario overrides the default --difficulty
                    if self.scenario is not None:
                        self.sim.set_scenario_depth(self.scenario)
                    else:
                        self.sim.set_difficulty(self.difficulty)
            except (ModuleNotFoundError, ImportError):
                pass

            tool_registry = load_tools(
                self.task_id, config=fast_cfg, sim=self.sim)
            if self.verbose:
                print(f"[RuntimeB] Loaded benchmark tools")
        except Exception as exc:
            import logging
            task_num = int(''.join(c for c in self.task_id if c.isdigit()) or '0')
            if task_num >= 12:
                raise RuntimeError(
                    f"Failed to load required benchmark tools for sim task "
                    f"'{self.task_id}': {exc}"
                ) from exc
            logging.getLogger(__name__).warning(
                "Failed to load benchmark tools for %s: %s — "
                "agents will proceed with coordination tools only",
                self.task_id, exc)
            if self.verbose:
                import traceback
                traceback.print_exc()

        # 5. Load pre-generated prompts + create runners
        prompts_dir = self.workspace / "prompts" / "runtime_b"
        if not prompts_dir.is_dir():
            prompts_dir = self.workspace / "prompts"  # legacy flat layout
        runners: list[AgentRunner] = []
        for agent in ir["agents"]:
            agent_id = agent["id"]

            # Read pre-generated prompt
            prompt_path = prompts_dir / f"{agent_id}.md"
            if not prompt_path.exists():
                raise FileNotFoundError(
                    f"Missing prompt: {prompt_path}")
            prompt = prompt_path.read_text() + _COORD_FOOTER

            # Combine domain tools + coordination tools
            domain_schemas = []
            if tool_registry:
                domain_schemas = tool_registry.openai_schemas(agent_id)
            all_schemas = domain_schemas + COORD_TOOL_SCHEMAS

            config = AgentConfig(
                agent_id=agent_id,
                system_prompt=prompt,
                tool_schemas=all_schemas,
                model=self.model,
                api_key=self.api_key,
                verbose=self.verbose,
            )
            runner = AgentRunner(config, coord, tool_registry, event_bus=event_bus)
            runners.append(runner)

            if self.verbose:
                print(f"[RuntimeB] Created agent: {agent_id} "
                      f"({len(domain_schemas)} domain + "
                      f"{len(COORD_TOOL_SCHEMAS)} coord tools)")

        # 6. Emit run.start
        if event_bus:
            await event_bus.emit("run.start", {
                "agents": [a["id"] for a in ir["agents"]],
                "channels": [c["id"] for c in ir.get("channels", [])],
                "resources": [r["id"] for r in ir.get("resources", [])],
            })

        # 7. Run all agents concurrently
        tasks = [asyncio.create_task(r.run(max_rounds=self.max_rounds))
                 for r in runners]
        try:
            done, pending = await asyncio.wait(
                tasks, timeout=timeout,
                return_when=asyncio.ALL_COMPLETED,
            )
            dur = time.monotonic() - t0

            if pending:
                # Cancel still-running tasks
                for t in pending:
                    t.cancel()
                # Emit timeout for timed-out agents
                agent_results = []
                for runner, task in zip(runners, tasks):
                    if task in done and not task.cancelled():
                        agent_results.append(task.result())
                    else:
                        ar = AgentResult(
                            runner.config.agent_id,
                            runner._steps, "timeout", dur,
                            trace=list(runner.trace),
                            input_tokens=runner._total_input_tokens,
                            output_tokens=runner._total_output_tokens,
                        )
                        agent_results.append(ar)
                        if event_bus:
                            await event_bus.emit("agent.done", {
                                "agent_id": runner.config.agent_id,
                                "status": "timeout", "steps": runner._steps,
                                "duration": dur,
                                "input_tokens": runner._total_input_tokens,
                                "output_tokens": runner._total_output_tokens,
                            })

                run_result = RunResult(
                    success=False,
                    agent_results=agent_results,
                    duration=dur,
                    error=f"Timeout after {timeout}s",
                    state_violations=tracker.violations if tracker else [],
                )
            else:
                results = [t.result() for t in tasks]
                all_ok = all(r.status == "completed" for r in results)
                run_result = RunResult(
                    success=all_ok,
                    agent_results=results,
                    duration=dur,
                    state_violations=tracker.violations if tracker else [],
                    corrections_exceeded=[r.agent_id for r in results
                                          if r.status == "correction_failed"],
                )

        except Exception as e:
            dur = time.monotonic() - t0
            agent_results = []
            for runner in runners:
                agent_results.append(AgentResult(
                    runner.config.agent_id,
                    runner._steps, "error", dur, str(e),
                    trace=list(runner.trace),
                ))
            run_result = RunResult(
                success=False,
                agent_results=agent_results,
                duration=dur,
                error=str(e),
                state_violations=tracker.violations if tracker else [],
            )

        # 8. Emit run.done + shutdown live server
        if event_bus:
            run_done_data = {
                "success": run_result.success,
                "duration": run_result.duration,
                "error": run_result.error,
            }
            if self.sim is not None:
                run_done_data["sim"] = {
                    "progress": self.sim.progress,
                    "violations": [
                        {"type": v.violation_type, "agent": v.agent,
                         "tool": v.tool, "message": v.message}
                        for v in self.sim.violations
                    ],
                }
            if tracker and tracker.violation_count > 0:
                run_done_data["protocol"] = {
                    "violations": [
                        {"agent": v.agent, "state": v.current_state,
                         "operation": v.operation, "args": v.args}
                        for v in tracker.violations
                    ],
                    "final_states": tracker.current_states,
                }
            await event_bus.emit("run.done", run_done_data)
            # Give browser a moment to receive final events
            await asyncio.sleep(1.0)
            await event_bus.close()

        if live_server:
            from tracefix.runtime.monitoring.live_server import stop_live_server
            await stop_live_server(live_server)

        return run_result
