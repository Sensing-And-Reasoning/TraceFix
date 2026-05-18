"""RuntimeBase1 orchestrator: group chat baseline.

Agents communicate via a shared message board (SharedChat).
No locks, channels, or protocol steps. Uses ir.json only for agent list.

Reuses tracefix.runtime.monitoring.agent_runner.AgentRunner directly via the Chat Adapter
pattern: ChatCoordinationContext duck-types CoordinationContext so
AgentRunner dispatches send_message/receive_message to the group chat.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from tracefix.runtime.monitoring.agent_runner import AgentRunner, AgentConfig, AgentResult
from tracefix.runtime.monitoring.orchestrator import RunResult
from tracefix.runtime.baselines.shared_chat.chat_coord import (
    SharedChat, ChatCoordinationContext, CHAT_TOOL_SCHEMAS, CHAT_FOOTER,
)
from tracefix.runtime.baselines.shared_chat.prompt_gen import generate_b1_prompt


_ROOT = Path(__file__).resolve().parent.parent


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _load_task_desc(task_id: str) -> str:
    """Load task description from benchmark/descriptions."""
    task_dir = _ROOT / "benchmark" / "descriptions" / task_id
    desc_path = task_dir / "description.md"
    if desc_path.exists():
        return desc_path.read_text()
    raise FileNotFoundError(f"No description.md found for task '{task_id}'")


class RuntimeBase1:
    """Baseline 1: Group chat runtime — no locks, no channels, no protocol.

    Uses tracefix.runtime.monitoring.agent_runner.AgentRunner with ChatCoordinationContext
    (adapter pattern) for code reuse and experimental fairness.
    """

    def __init__(
        self,
        task_id: str,
        experiment: str = "",
        model: str = "gpt-5-mini",
        api_key: str = "",
        verbose: bool = False,
        workspace: Path | None = None,
        live: bool = False,
        live_port: int = 8765,
        scenario: int | None = None,
        difficulty: int = 1,
        tool_time: float | None = None,
        seed: int | None = None,
        max_rounds: int = 50,
    ):
        self.task_id = task_id
        self.experiment = experiment
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
        if workspace:
            self.workspace = workspace
        elif experiment:
            self.workspace = _ROOT / "workspace" / experiment / task_id
        else:
            raise ValueError("Must provide either --experiment or --workspace")

    async def run(self, timeout: float = 120.0) -> RunResult:
        t0 = time.monotonic()

        # 1. Load IR (for agent list only)
        ir = _load_json(self.workspace / "ir.json")

        # 2. Load task description
        task_desc = _load_task_desc(self.task_id)

        # 3. Create shared chat (coord created after event_bus below)
        agent_ids = [a["id"] for a in ir["agents"]]
        chat = SharedChat(agent_ids)

        # 4. Live visualization setup
        event_bus = None
        live_server = None
        if self.live:
            from tracefix.runtime.monitoring.event_bus import EventBus
            from tracefix.runtime.monitoring.live_server import start_live_server
            event_bus = EventBus()
            # Build a star-topology IR for visualization
            star_ir = self._build_star_ir(ir)
            title = f"[B1] Task {self.task_id} | {self.model}"
            live_server = await start_live_server(
                star_ir, event_bus, port=self.live_port, title=title,
                model=self.model)
            url = f"http://127.0.0.1:{self.live_port}"
            print(f"[Base1] Live view: {url}")
            import webbrowser
            webbrowser.open(url)

        # Create coord adapter with event_bus for live chat visualization
        coord = ChatCoordinationContext(chat, agent_ids, event_bus=event_bus)
        self._coord = coord

        # 5. Load domain tools (matches tracefix.runtime.monitoring: zero delay)
        tool_registry = None
        self.sim = None
        try:
            from benchmark.tools import load_tools, ToolConfig
            import importlib as _imp

            fast_cfg = ToolConfig(min_delay=0.0, max_delay=0.0,
                                  fail_probability=0.0)

            # Auto-discover sim module for this task
            try:
                sim_mod = _imp.import_module(
                    f"benchmark.environments.{self.task_id}.sim")
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
                    if self.scenario is not None:
                        self.sim.set_scenario_depth(self.scenario)
                    else:
                        self.sim.set_difficulty(self.difficulty)
            except (ModuleNotFoundError, ImportError):
                pass

            tool_registry = load_tools(
                self.task_id, config=fast_cfg, sim=self.sim)
            if self.verbose:
                print(f"[Base1] Loaded benchmark tools")
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to load benchmark tools for %s: %s",
                self.task_id, exc)
            if self.verbose:
                import traceback
                traceback.print_exc()

        # 6. Create agent runners (reuse tracefix.runtime.monitoring's AgentRunner directly)
        runners: list[AgentRunner] = []
        for agent in ir["agents"]:
            agent_id = agent["id"]

            prompt = generate_b1_prompt(agent_id, task_desc, ir) + CHAT_FOOTER

            domain_schemas = []
            if tool_registry:
                domain_schemas = tool_registry.openai_schemas(agent_id)
            all_schemas = domain_schemas + CHAT_TOOL_SCHEMAS

            config = AgentConfig(
                agent_id=agent_id,
                system_prompt=prompt,
                tool_schemas=all_schemas,
                model=self.model,
                api_key=self.api_key,
                verbose=self.verbose,
            )
            runner = AgentRunner(
                config, coord, tool_registry, event_bus=event_bus)
            runners.append(runner)

            if self.verbose:
                print(f"[Base1] Created agent: {agent_id} "
                      f"({len(domain_schemas)} domain + "
                      f"{len(CHAT_TOOL_SCHEMAS)} chat tools)")

        # 7. Emit run.start
        if event_bus:
            await event_bus.emit("run.start", {
                "agents": agent_ids,
                "channels": ["group_chat"],
                "resources": [],
            })

        # 8. Run all agents concurrently
        tasks = [asyncio.create_task(r.run(max_rounds=self.max_rounds))
                 for r in runners]
        try:
            done, pending = await asyncio.wait(
                tasks, timeout=timeout,
                return_when=asyncio.ALL_COMPLETED,
            )
            dur = time.monotonic() - t0

            if pending:
                for t in pending:
                    t.cancel()
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
                )
            else:
                results = [t.result() for t in tasks]
                all_ok = all(r.status == "completed" for r in results)
                run_result = RunResult(
                    success=all_ok,
                    agent_results=results,
                    duration=dur,
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
            )

        # 9. Emit run.done + shutdown live server
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
            await event_bus.emit("run.done", run_done_data)
            await asyncio.sleep(1.0)
            await event_bus.close()

        if live_server:
            from tracefix.runtime.monitoring.live_server import stop_live_server
            await stop_live_server(live_server)

        return run_result

    @staticmethod
    def _build_star_ir(ir: dict) -> dict:
        """Build a star-topology IR for visualization.

        All agents connect to a central 'group_chat' node via a single
        broadcast channel whose ID is 'group_chat' — matching the
        channel_id agents pass to send_message/receive_message so that
        message counts in both live and static visualizations are correct.
        """
        agents = ir["agents"]
        agent_ids = [a["id"] for a in agents]
        return {
            "agents": agents + [{"id": "group_chat", "initial_state": "hub"}],
            "resources": [],
            "channels": [{
                "id": "group_chat",
                "from": agent_ids,
                "to": ["group_chat"],
                "labels": ["message"],
            }],
            "states": {},
        }
