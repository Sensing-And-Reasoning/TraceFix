"""Swarm-IDE style async execution engine for verified IR protocols.

Architecture (mirrors swarm-ide):
- Each agent has its own AgentRunner with an asyncio.Event (sleep/wake)
- Stores (MessageStore, LockStore, CounterStore) hold protocol state
- Send/release/increment effects wake relevant agents via precomputed wake maps
- Agents poll stores for guard satisfaction (processUntilIdle pattern)
- No global lock needed — asyncio cooperative scheduling ensures atomicity
  within synchronous _try_step() calls (no await between check and mutate)
"""

import asyncio
import random
import time
from dataclasses import dataclass, field

from tracefix.runtime.enforcement.policy import AgentPolicy, RandomPolicy
from tracefix.runtime.enforcement.store import MessageStore, LockStore, CounterStore


# ---------------------------------------------------------------------------
# Trace & Result
# ---------------------------------------------------------------------------

@dataclass
class TraceEvent:
    step: int
    timestamp: float
    agent: str
    from_state: str
    to_state: str
    guards: list[str] = field(default_factory=list)
    effects: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)


@dataclass
class RunResult:
    success: bool
    steps: int
    duration: float
    trace: list[TraceEvent]
    final_states: dict[str, str]
    error: str | None = None
    final_locks: dict[str, str | None] = field(default_factory=dict)
    final_channels: dict[str, int] = field(default_factory=dict)
    final_counters: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AgentRunner — per-agent sleep/wake/poll loop (like swarm-ide AgentRunner)
# ---------------------------------------------------------------------------

class AgentRunner:
    """One runner per agent.  Lifecycle: sleep → wake → processUntilIdle → sleep."""

    def __init__(self, agent_id: str, initial_state: str, states: dict, runtime: "Runtime"):
        self.agent_id = agent_id
        self._state = initial_state
        self._states = states
        self._runtime = runtime
        self._wake = asyncio.Event()
        self._done = False
        # Persisted recv context: accumulates recv guard info across auto-advance
        # chains until consumed by _filter_by_recv_context at a DECISION state.
        self._recv_context: list[dict] = []

    @property
    def state(self) -> str:
        return self._state

    @property
    def done(self) -> bool:
        return self._done

    def wakeup(self, reason: str = ""):
        """Called by Runtime when a relevant store change occurs."""
        self._wake.set()

    async def loop(self) -> str:
        """Main loop.  Returns final state when agent reaches terminal."""
        self._wake.set()  # initial wake — start processing immediately

        while not self._done:
            await self._wake.wait()
            self._wake.clear()
            await self._process_until_idle()

        return self._state

    async def _process_until_idle(self):
        """Keep executing actions until no more progress can be made."""
        while not self._done:
            progressed = await self._try_step()
            if not progressed:
                return  # nothing enabled → go back to sleep
            await asyncio.sleep(0)  # yield to let other runners run

    def _filter_by_recv_context(
        self, enabled: list[dict], context_log: list[dict],
    ) -> list[dict]:
        """Narrow decision options when auto-advance consumed a receive.

        If the preceding auto-advance consumed a message from channel C whose
        ``from`` agent is X, and the current decision has send actions targeting
        different agents, keep only actions whose send targets agent X.

        This prevents the LLM from responding to the wrong agent (e.g. reviewer
        receives from backend but accidentally sends approval to frontend).
        """
        if not context_log or len(enabled) <= 1:
            return enabled

        # Collect source agents from all recv guards in context_log.
        # _channel_meta["from"] is always a list (normalized in Runtime._init).
        meta = self._runtime._channel_meta
        source_agents: set[str] = set()
        for step in context_log:
            for g in step.get("guards", []):
                # g looks like "recv(ch_be_rev,None)" or "recv(ch_be_rev,label)"
                if g.startswith("recv("):
                    ch_name = g[5:].split(",")[0]
                    if ch_name in meta:
                        source_agents.update(meta[ch_name]["from"])

        if not source_agents:
            return enabled

        # Check if the decision actions send to different agents
        def _send_targets(action: dict) -> set[str]:
            sends = action.get("send", [])
            if isinstance(sends, dict):
                sends = [sends]
            targets: set[str] = set()
            for s in sends:
                ch = s.get("channel", "")
                if ch in meta:
                    targets.update(meta[ch]["to"])
            return targets

        # Only filter if at least some actions have send effects
        actions_with_sends = [a for a in enabled if _send_targets(a)]
        if not actions_with_sends:
            return enabled

        # Keep actions whose send targets overlap with source agents
        filtered = [
            a for a in enabled
            if not _send_targets(a) or _send_targets(a) & source_agents
        ]

        # Safety: never filter to empty
        return filtered if filtered else enabled

    @staticmethod
    def _classify(enabled: list[dict]) -> str:
        """Classify the current step based on enabled actions.

        Returns:
            "decision" — multiple enabled actions, LLM must choose
            "auto"     — single action with guards/effects, auto-advance
            "business" — single action with no guards/effects, LLM does domain work
        """
        if len(enabled) > 1:
            return "decision"
        action = enabled[0]
        # "guard" = local variable check; "increment" = local variable mutation.
        # Both are pure coordination ops that should be auto-advanced.
        has_guards  = bool(action.get("receive") or action.get("acquire")
                          or action.get("guard"))
        has_effects = bool(action.get("send") or action.get("release")
                          or action.get("increment"))
        if has_guards or has_effects:
            return "auto"
        return "business"

    async def _try_step(self) -> bool:
        """Try to execute one or more actions at the current state.

        Coordination states (single action with guards/effects) are auto-advanced
        without calling the LLM.  The engine chains through them until it reaches
        a state that needs LLM input (BUSINESS or DECISION) or gets blocked.

        Auto-advanced steps are accumulated in ``context_log`` and passed to the
        policy so the LLM knows what coordination happened since its last call.
        """
        context_log: list[dict] = []

        while True:
            sdef = self._states.get(self._state)
            if sdef is None:
                raise RuntimeError(f"Agent {self.agent_id}: unknown state '{self._state}'")

            actions = sdef.get("actions", [])
            if not actions:
                # TERMINAL
                self._done = True
                self._runtime._on_agent_terminated(self.agent_id)
                return bool(context_log)

            # Phase 1: find enabled actions (sync)
            enabled = [a for a in actions if self._runtime._check_guards(a, self.agent_id)]

            # While-loop filtering: if any *enabled* guarded action is satisfied,
            # exclude unguarded actions so the agent can't exit the loop prematurely.
            # We check only `enabled` (not all `actions`) to avoid false positives
            # from guarded actions that are blocked on receive/acquire.
            if any("guard" in a for a in actions):
                guard_active = any(
                    "guard" in a and self._runtime._check_local_guard(a, self.agent_id)
                    for a in enabled
                )
                if guard_active:
                    enabled = [a for a in enabled if "guard" in a]

            if not enabled:
                return bool(context_log)  # blocked — sleep

            classification = self._classify(enabled)

            if classification == "auto":
                # Auto-advance: execute the single coordination action without LLM
                pick = enabled[0]
                from_state = self._state
                guard_descs = self._runtime._consume_guards(pick, self.agent_id)
                effect_descs = self._runtime._apply_effects(pick, self.agent_id)
                self._state = pick["target"]
                self._runtime._record(self.agent_id, from_state, self._state,
                                      guard_descs, effect_descs, [])
                step_entry = {
                    "from": from_state,
                    "to": self._state,
                    "guards": guard_descs,
                    "effects": effect_descs,
                }
                context_log.append(step_entry)
                # Persist recv guards so filtering works even if a BUSINESS
                # state separates the recv from a later DECISION.
                # Replace (not append) — only the most recent recv matters.
                if any(g.startswith("recv(") for g in guard_descs):
                    self._recv_context = [step_entry]
                await asyncio.sleep(0)  # yield between chained steps
                continue  # loop → check next state

            else:
                # BUSINESS or DECISION — need LLM
                # Filter decision options using persisted recv context
                # (survives across _try_step calls, unlike context_log)
                all_recv_ctx = self._recv_context + context_log
                filtered = self._filter_by_recv_context(enabled, all_recv_ctx)
                # Clear persisted recv context after use at any non-auto state.
                # This prevents a stale recv context from influencing future decisions
                # if a guard becomes invalid and forces a retry.
                self._recv_context.clear()

                policy = self._runtime._policy
                idx, tool_calls = await policy.choose_action(
                    self.agent_id, self._state, filtered,
                    context=context_log if context_log else None,
                )
                pick = filtered[idx]

                # Re-validate guard after async gap
                if not self._runtime._check_guards(pick, self.agent_id):
                    return bool(context_log)  # guard invalidated — retry next wake

                from_state = self._state
                guard_descs = self._runtime._consume_guards(pick, self.agent_id)
                effect_descs = self._runtime._apply_effects(pick, self.agent_id)
                self._state = pick["target"]
                self._runtime._record(self.agent_id, from_state, self._state,
                                      guard_descs, effect_descs, tool_calls)

                # Persist recv from LLM-chosen action so the NEXT decision
                # (possibly in a later _try_step) can filter by sender.
                if any(g.startswith("recv(") for g in guard_descs):
                    self._recv_context = [{
                        "from": from_state,
                        "to": self._state,
                        "guards": guard_descs,
                        "effects": effect_descs,
                    }]
                return True


# ---------------------------------------------------------------------------
# Runtime — orchestrator (like swarm-ide AgentRuntime)
# ---------------------------------------------------------------------------

class Runtime:
    """Creates stores and runners from IR, manages wake notifications."""

    def __init__(self, ir: dict, seed: int | None = None,
                 policy: AgentPolicy | None = None,
                 event_bus: "EventBus | None" = None):
        self._rng = random.Random(seed)
        self._policy: AgentPolicy = policy or RandomPolicy(self._rng)
        self._event_bus = event_bus
        self._t0 = time.monotonic()
        self._step = 0
        self._trace: list[TraceEvent] = []

        # Stores
        self.messages = MessageStore()
        self.locks = LockStore()
        self.counters = CounterStore()

        # Local variables: agent_id → {var_name: value}
        self._local_vars: dict[str, dict[str, int]] = {}

        # Wake maps: which agents to wake when a channel/resource changes
        self._channel_wake: dict[str, set[str]] = {}   # ch → {agents that recv}
        self._resource_wake: dict[str, set[str]] = {}   # res → {agents that acquire}

        # Channel topology: ch_id → {"from": agent, "to": agent}
        self._channel_meta: dict[str, dict[str, str]] = {}

        # Runners
        self._runners: dict[str, AgentRunner] = {}
        self._init(ir)

    def _init(self, ir: dict):
        # Resources
        for r in ir.get("resources", []):
            if r["type"] == "Lock":
                self.locks.init_lock(r["id"])
            elif r["type"] == "Counter":
                self.counters.init_counter(r["id"], r.get("config", {}).get("initial", 0))

        # Local variables (from states.json)
        for var_name, info in ir.get("local_variables", {}).items():
            agent_id = info["agent"]
            self._local_vars.setdefault(agent_id, {})[var_name] = info["initial"]

        # Channels — store normalized lists so _filter_by_recv_context handles
        # both single-agent ("from": "a") and multi-agent ("from": ["a", "b"]) IR.
        for ch in ir.get("channels", []):
            self.messages.init_channel(ch["id"])
            from_val = ch.get("from", "")
            to_val = ch.get("to", "")
            self._channel_meta[ch["id"]] = {
                "from": [from_val] if isinstance(from_val, str) else list(from_val),
                "to":   [to_val]   if isinstance(to_val,   str) else list(to_val),
            }

        # State lookup
        states: dict[str, dict] = {s["id"]: s for s in ir["states"]}

        # Build wake maps by scanning all states
        for state in ir["states"]:
            agent_id = state["agent"]
            for action in state.get("actions", []):
                for recv in action.get("receive", []):
                    self._channel_wake.setdefault(recv["channel"], set()).add(agent_id)
                for rid in action.get("acquire", []):
                    self._resource_wake.setdefault(rid, set()).add(agent_id)

        # Create runners
        for a in ir["agents"]:
            self._runners[a["id"]] = AgentRunner(a["id"], a["initial_state"], states, self)

    # --- Guard checking (read-only) ---

    def _check_local_guard(self, action: dict, agent_id: str) -> bool:
        """Check if a local variable guard is satisfied (or absent)."""
        guard = action.get("guard")
        if guard is None:
            return True
        var_name = guard["var"]
        value = guard["value"]
        current = self._local_vars.get(agent_id, {}).get(var_name, 0)
        op = guard["op"]
        if op == "<":
            return current < value
        elif op == "<=":
            return current <= value
        elif op == ">":
            return current > value
        elif op == ">=":
            return current >= value
        elif op == "==":
            return current == value
        elif op == "!=":
            return current != value
        return True

    def _check_guards(self, action: dict, agent_id: str = "") -> bool:
        if not self._check_local_guard(action, agent_id):
            return False
        for r in action.get("receive", []):
            if not self.messages.peek(r["channel"], r.get("label")):
                return False
        for rid in action.get("acquire", []):
            if rid in self.locks and not self.locks.is_free(rid):
                return False
            if rid in self.counters and self.counters.value(rid) <= 0:
                return False
        return True

    # --- Guard consumption (mutates stores) ---

    def _consume_guards(self, action: dict, agent_id: str) -> list[str]:
        descs: list[str] = []
        for r in action.get("receive", []):
            msg = self.messages.try_consume(r["channel"], r.get("label"))
            if msg:
                descs.append(f"recv({r['channel']},{r.get('label')})")
        for rid in action.get("acquire", []):
            if rid in self.locks:
                ok = self.locks.try_acquire(rid, agent_id)
                if not ok:
                    # Should be unreachable: _check_guards passed with no await gap
                    raise RuntimeError(
                        f"BUG: {agent_id} failed to acquire lock '{rid}' — "
                        "guard was satisfied but try_acquire failed"
                    )
                descs.append(f"acquire({rid})")
            elif rid in self.counters:
                ok = self.counters.try_decrement(rid)
                if not ok:
                    raise RuntimeError(
                        f"BUG: {agent_id} failed to decrement counter '{rid}' — "
                        "guard was satisfied but try_decrement failed"
                    )
                descs.append(f"dec({rid})")
        return descs

    # --- Effect execution (mutates stores + wakes agents) ---

    def _apply_effects(self, action: dict, agent_id: str) -> list[str]:
        descs: list[str] = []
        for s in action.get("send", []):
            ch, lbl = s["channel"], s.get("label", "")
            self.messages.send(ch, lbl, agent_id)
            descs.append(f"send({ch},{lbl})")
            # Wake agents that receive from this channel
            self._wake_agents(self._channel_wake.get(ch, set()), exclude=agent_id)
        for rid in action.get("release", []):
            released = False
            if rid in self.locks:
                self.locks.release(rid, agent_id)
                descs.append(f"release({rid})")
                released = True
            elif rid in self.counters:
                self.counters.increment(rid)
                descs.append(f"inc({rid})")
                released = True
            # Only wake waiting agents when the release actually happened
            if released:
                self._wake_agents(self._resource_wake.get(rid, set()), exclude=agent_id)

        # Local variable increment
        incr = action.get("increment")
        if incr:
            self._local_vars.setdefault(agent_id, {})[incr] = \
                self._local_vars.get(agent_id, {}).get(incr, 0) + 1
            descs.append(f"inc_local({incr})")

        return descs

    # --- Wake helpers ---

    def _wake_agents(self, agent_ids: set[str], exclude: str = ""):
        for aid in agent_ids:
            if aid != exclude and aid in self._runners and not self._runners[aid].done:
                self._runners[aid].wakeup()

    def _emit(self, event_type: str, data: dict):
        """Emit an event if an event bus is attached (fire-and-forget)."""
        if self._event_bus is not None:
            asyncio.create_task(self._event_bus.emit(event_type, data))

    def _on_agent_terminated(self, agent_id: str):
        """Called when an agent reaches a terminal state."""
        # Notify the policy so it can tear down any background loop
        policy = self._policy
        if hasattr(policy, "notify_done"):
            asyncio.create_task(policy.notify_done(agent_id))

        self._emit("agent.done", {
            "agent_id": agent_id,
            "final_state": self._runners[agent_id].state,
        })
        # Wake others so they can re-evaluate (e.g. if waiting for this agent)
        for aid, runner in self._runners.items():
            if aid != agent_id and not runner.done:
                runner.wakeup()

    # --- Trace ---

    def _record(self, agent: str, from_state: str, to_state: str,
                guards: list[str], effects: list[str],
                tool_calls: list[dict] | None = None):
        self._step += 1
        ts = time.monotonic() - self._t0
        self._trace.append(TraceEvent(
            step=self._step,
            timestamp=ts,
            agent=agent,
            from_state=from_state,
            to_state=to_state,
            guards=guards,
            effects=effects,
            tool_calls=tool_calls or [],
        ))
        self._emit("step", {
            "step": self._step,
            "agent_id": agent,
            "from_state": from_state,
            "to_state": to_state,
            "guards": guards,
            "effects": effects,
            "tool_calls": tool_calls or [],
            "timestamp": ts,
        })

    # --- Store snapshots ---

    def _snapshot_locks(self) -> dict[str, str | None]:
        return dict(self.locks._locks)

    def _snapshot_channels(self) -> dict[str, int]:
        return {ch: len(msgs) for ch, msgs in self.messages._channels.items()}

    def _snapshot_counters(self) -> dict[str, int]:
        return dict(self.counters._counters)

    # --- Run ---

    async def run(self, timeout: float = 5.0) -> RunResult:
        """Start all agent loops and wait for completion or timeout."""
        agent_ids = list(self._runners.keys())
        coros = [self._runners[aid].loop() for aid in agent_ids]

        self._emit("run.start", {"agents": agent_ids})

        t0 = time.monotonic()
        try:
            results = await asyncio.wait_for(asyncio.gather(*coros), timeout=timeout)
            dur = time.monotonic() - t0
            if hasattr(self._policy, "cleanup"):
                await self._policy.cleanup()
            final = dict(zip(agent_ids, results))
            result = RunResult(True, self._step, dur, self._trace, final,
                               final_locks=self._snapshot_locks(),
                               final_channels=self._snapshot_channels(),
                               final_counters=self._snapshot_counters())
            self._emit("run.done", {
                "success": True, "steps": self._step,
                "duration": dur, "final_states": final,
            })
            return result
        except asyncio.TimeoutError:
            dur = time.monotonic() - t0
            if hasattr(self._policy, "cleanup"):
                await self._policy.cleanup()
            error = f"Timeout after {timeout}s — likely deadlock"
            final = {aid: r.state for aid, r in self._runners.items()}
            self._emit("run.done", {
                "success": False, "steps": self._step,
                "duration": dur, "error": error,
            })
            return RunResult(
                success=False,
                steps=self._step,
                duration=dur,
                trace=self._trace,
                final_states=final,
                error=error,
                final_locks=self._snapshot_locks(),
                final_channels=self._snapshot_channels(),
                final_counters=self._snapshot_counters(),
            )
        except Exception as e:
            dur = time.monotonic() - t0
            if hasattr(self._policy, "cleanup"):
                await self._policy.cleanup()
            final = {aid: r.state for aid, r in self._runners.items()}
            self._emit("run.done", {
                "success": False, "steps": self._step,
                "duration": dur, "error": str(e),
            })
            return RunResult(
                success=False,
                steps=self._step,
                duration=dur,
                trace=self._trace,
                final_states=final,
                error=str(e),
                final_locks=self._snapshot_locks(),
                final_channels=self._snapshot_channels(),
                final_counters=self._snapshot_counters(),
            )


# ---------------------------------------------------------------------------
# Public API (unchanged)
# ---------------------------------------------------------------------------

async def run_protocol(
    ir: dict,
    *,
    seed: int | None = None,
    timeout: float = 5.0,
    policy: AgentPolicy | None = None,
    event_bus: "EventBus | None" = None,
) -> RunResult:
    """Execute an IR protocol concurrently.  Returns RunResult."""
    rt = Runtime(ir, seed=seed, policy=policy, event_bus=event_bus)
    return await rt.run(timeout=timeout)


def run_ir(
    ir: dict,
    *,
    seed: int | None = None,
    timeout: float = 5.0,
    policy: AgentPolicy | None = None,
    event_bus: "EventBus | None" = None,
) -> RunResult:
    """Synchronous convenience wrapper."""
    return asyncio.run(run_protocol(ir, seed=seed, timeout=timeout,
                                    policy=policy, event_bus=event_bus))
