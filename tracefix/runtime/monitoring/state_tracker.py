"""StateTracker: tracks per-agent state machine progress against states.json.

Validates that runtime coordination operations follow the verified
state machine extracted from TLC-checked PlusCal specs.

Compound actions (e.g., release + send in the same TLA+ action) use a
pending-ops pattern: the first matching op commits to an action, stores
remaining ops as pending, and subsequent ops are consumed from pending
before a state transition fires.
"""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _dedupe_hints(hints) -> list[dict]:
    """Order-preserving de-duplication of legal-action hint dicts."""
    seen: list[dict] = []
    for h in hints:
        if h not in seen:
            seen.append(h)
    return seen


@dataclass
class StateViolation:
    """A coordination operation that doesn't match any valid action."""
    agent: str
    current_state: str
    operation: str          # "acquire" | "release" | "send" | "receive"
    args: dict              # e.g. {"resource": "doc_lock"} or {"channel": "ch", "label": "submit"}
    valid_actions: list[dict]
    timestamp: float


class StateTracker:
    """Tracks per-agent state machine progress and validates operations.

    Thread-safety contract: This class is NOT internally synchronized.
    Callers MUST serialize all calls for the same ``agent_id`` externally
    (e.g., ``coord.py`` uses a per-agent ``asyncio.Lock``).  Calls for
    *different* agents are already independent and may run concurrently.
    """

    def __init__(self, states_data: dict):
        # Build state_map: agent_id → state_id → actions list
        self._state_map: dict[str, dict[str, list[dict]]] = {}
        for state in states_data.get("states", []):
            agent = state["agent"]
            if agent not in self._state_map:
                self._state_map[agent] = {}
            self._state_map[agent][state["id"]] = state["actions"]

        # Optional per-state BUSINESS-task descriptions (observability plane only;
        # ignored by the verified control core). Keyed by state id.
        self._state_tasks: dict[str, str] = {
            s["id"]: s["task"]
            for s in states_data.get("states", [])
            if s.get("task")
        }

        # Initialize current states
        self._current: dict[str, str] = dict(states_data.get("initial_states", {}))

        # Per-agent current BUSINESS phase = the no-op "business" state the agent is
        # currently working in (auto-derived). The coordination current_state reads
        # the NEXT coord op because business states are skipped; this records which
        # business state the agent passed into. Telemetry only — never validated.
        self._current_phases: dict[str, str] = {}

        # Pending ops for compound actions: agent_id → {remaining, next_state}
        self._pending: dict[str, dict] = {}

        # Ambiguous candidate tracking for nondeterministic skip paths.
        # When multiple skip targets share the same first observable operation,
        # candidates are tracked NFA-style until subsequent ops disambiguate.
        # agent_id → [{"state", "remaining", "next_state"}, ...]
        self._candidates: dict[str, list[dict]] = {}

        # Violation log
        self._violations: list[StateViolation] = []

        # Counter variable tracking: var_name → current value
        self._counters: dict[str, int] = {}
        self._counter_agents: dict[str, str] = {}  # var_name → agent_id
        self._init_counters(states_data)

        # Auto-advance through initial skip states
        for agent_id in list(self._current):
            self._auto_advance(agent_id)

    @property
    def violations(self) -> list[StateViolation]:
        return list(self._violations)

    @property
    def current_states(self) -> dict[str, str]:
        return dict(self._current)

    @property
    def current_phases(self) -> dict[str, str]:
        """Per-agent current BUSINESS phase: the state id of the no-op business
        state the agent is working in, or absent when it is at a pure coordination
        step. Observability only — never affects validation."""
        return dict(self._current_phases)

    @property
    def state_tasks(self) -> dict[str, str]:
        """Optional per-state business-task descriptions (state id -> prose)."""
        return dict(self._state_tasks)

    @property
    def violation_count(self) -> int:
        return len(self._violations)

    @property
    def counter_values(self) -> dict[str, int]:
        return dict(self._counters)

    # --- Counter tracking ---

    def _init_counters(self, states_data: dict):
        """Initialize counters from local_variables or by discovering from actions."""
        local_vars = states_data.get("local_variables", {})
        if local_vars:
            for var, info in local_vars.items():
                self._counters[var] = info.get("initial", 0)
                self._counter_agents[var] = info.get("agent", "")
        else:
            self._discover_counters()

    def _discover_counters(self):
        """Fallback: scan all actions for guard.var and increment fields, init to 0."""
        for agent_id, states in self._state_map.items():
            for actions in states.values():
                for action in actions:
                    guard = action.get("guard")
                    if guard and "var" in guard:
                        var = guard["var"]
                        if var not in self._counters:
                            self._counters[var] = 0
                            self._counter_agents[var] = agent_id
                    inc = action.get("increment")
                    if inc:
                        inc_list = [inc] if isinstance(inc, str) else inc
                        for var in inc_list:
                            if var not in self._counters:
                                self._counters[var] = 0
                                self._counter_agents[var] = agent_id

    @staticmethod
    def _evaluate_guard(guard: dict, counters: dict[str, int]) -> bool:
        """Evaluate a guard condition against current counter values."""
        var = guard["var"]
        op = guard["op"]
        value = guard["value"]
        current = counters.get(var, 0)
        if op == "<":
            return current < value
        if op == "<=":
            return current <= value
        if op == ">":
            return current > value
        if op == ">=":
            return current >= value
        if op in ("=", "=="):
            return current == value
        if op in ("!=", "#"):
            return current != value
        logger.warning("Unknown guard operator: %s", op)
        return True  # permissive fallback

    def _filter_actions_by_guard(self, actions: list[dict]) -> list[dict]:
        """Filter actions using while-loop semantics for guards.

        Guarded actions are enabled when their guard is true.
        Unguarded actions are enabled only when ALL guards in the state are false
        (i.e., the while-loop exit branch).
        If no guards are present, all actions pass through unchanged.
        """
        if not self._counters:
            return actions

        guarded = []
        unguarded = []
        has_any_guard = False

        for action in actions:
            guard = action.get("guard")
            if guard:
                has_any_guard = True
                if self._evaluate_guard(guard, self._counters):
                    guarded.append(action)
            else:
                unguarded.append(action)

        if not has_any_guard:
            return actions

        # While-loop semantics: if any guarded action is enabled, take those
        if guarded:
            return guarded
        # All guards false → loop exit: take unguarded actions
        return unguarded

    def _apply_increment(self, action: dict):
        """Increment counters specified in the action's increment field."""
        inc = action.get("increment")
        if not inc:
            return
        inc_list = [inc] if isinstance(inc, str) else inc
        for var in inc_list:
            if var in self._counters:
                self._counters[var] += 1
                logger.debug("Counter %s incremented to %d", var, self._counters[var])

    def can_terminate(self, agent_id: str) -> bool:
        """Check if an agent can reach a terminal state from current state.

        Follows skip chains and guard filtering recursively. Returns True if
        the agent is already in a terminal state or can reach one via skip
        actions that pass guard filtering with current counter values.
        """
        if agent_id not in self._current:
            return True  # unknown agent — don't block
        state_id = self._current[agent_id]
        return self._can_reach_terminal(agent_id, state_id, set())

    def _can_reach_terminal(self, agent_id: str, state_id: str,
                            visited: set[str]) -> bool:
        if state_id in visited:
            return False
        visited.add(state_id)

        actions = self._state_map.get(agent_id, {}).get(state_id, [])
        if not actions:
            return True  # terminal state

        filtered = self._filter_actions_by_guard(actions)
        for action in filtered:
            if self._is_skip_action(action):
                if self._can_reach_terminal(agent_id, action["next_state"], visited):
                    return True
        return False

    # --- Corrective guidance (read-only) ---

    def legal_actions(self, agent_id: str) -> list[dict]:
        """The coordination operations legal from the agent's current position.

        Read-only. Each hint is e.g. ``{"op": "acquire", "resource": "PROD_DB"}``,
        ``{"op": "send", "channel": "c", "label": "go"}``, or ``{"op": "done"}``
        for a terminal state. Skip-resolved + guard-filtered; reflects pending /
        candidate remaining ops when mid-compound-action. Used to turn a rejected
        coordination call into "here is what you may legally do now".
        """
        if agent_id not in self._current:
            return []
        if agent_id in self._pending:
            return _dedupe_hints(
                self._op_hint(t, a) for t, a in self._pending[agent_id]["remaining"])
        if agent_id in self._candidates:
            hints: list[dict] = []
            for cand in self._candidates[agent_id]:
                if cand["remaining"]:
                    t, a = cand["remaining"][0]
                    hints.append(self._op_hint(t, a))
            return _dedupe_hints(hints)

        state_id = self._resolve_skip_chain(agent_id, self._current[agent_id])
        actions = self._filter_actions_by_guard(
            self._state_map.get(agent_id, {}).get(state_id, []))
        if not actions:
            return [{"op": "done"}]

        hints = []
        for action in actions:
            if self._is_skip_action(action):
                target = self._resolve_skip_chain(agent_id, action["next_state"])
                target_actions = self._state_map.get(agent_id, {}).get(target, [])
                if not target_actions:
                    hints.append({"op": "done"})
                for ta in self._filter_actions_by_guard(target_actions):
                    hints.extend(self._action_op_hints(ta))
            else:
                hints.extend(self._action_op_hints(action))
        return _dedupe_hints(hints)

    def check_op(self, agent_id: str, op_type: str,
                 op_args: dict) -> tuple[bool, list[dict]]:
        """Read-only legality check: would this op match a legal action *now*?

        Runs the real matching gate (``_try_match``) against a snapshot of the
        agent's position, then restores the position — so there is zero logic
        drift from the committing path. A miss still records a ``StateViolation``
        (kept after restore) so the monitoring record is accurate; on a miss the
        legal next actions are returned for corrective guidance.

        MUST be called synchronously (no ``await`` between snapshot and restore);
        ``coord.py`` calls it under its per-agent lock.
        """
        if agent_id not in self._current:
            return False, []
        snap = self._snapshot(agent_id)
        ok = self._try_match(agent_id, op_type, op_args)
        self._restore(agent_id, snap)  # restore position; keep any recorded violation
        return ok, ([] if ok else self.legal_actions(agent_id))

    def correction_streak(self, agent_id: str) -> int:
        """Number of trailing violations for ``agent_id`` at its current state.

        Resets to 0 once the agent makes a legal move (its current state changes),
        so the dispatcher can cap *unrecovered* corrections at one position.
        """
        state_id = self._current.get(agent_id)
        streak = 0
        for v in reversed(self._violations):
            if v.agent != agent_id:
                continue
            if v.current_state == state_id:
                streak += 1
            else:
                break
        return streak

    # --- Snapshot / restore (for read-only check_op) ---

    def _snapshot(self, agent_id: str) -> dict:
        return {
            "current": self._current.get(agent_id),
            "pending": copy.deepcopy(self._pending.get(agent_id)),
            "candidates": copy.deepcopy(self._candidates.get(agent_id)),
            "current_phases": self._current_phases.get(agent_id),
            "counters": dict(self._counters),
        }

    def _restore(self, agent_id: str, snap: dict):
        if snap["current"] is None:
            self._current.pop(agent_id, None)
        else:
            self._current[agent_id] = snap["current"]
        for store, key in ((self._pending, "pending"),
                           (self._candidates, "candidates"),
                           (self._current_phases, "current_phases")):
            if snap[key] is None:
                store.pop(agent_id, None)
            else:
                store[agent_id] = snap[key]
        self._counters.clear()
        self._counters.update(snap["counters"])

    @staticmethod
    def _action_op_hints(action: dict) -> list[dict]:
        """All observable coordination ops in an action, as readable hints."""
        hints: list[dict] = []
        for r in StateTracker._normalize_resource(action.get("acquire")):
            hints.append({"op": "acquire", "resource": r})
        for r in StateTracker._normalize_resource(action.get("release")):
            hints.append({"op": "release", "resource": r})
        for item in StateTracker._normalize_send_receive(action.get("send")):
            hints.append({"op": "send", "channel": item["channel"],
                          "label": item.get("label")})
        for item in StateTracker._normalize_send_receive(action.get("receive")):
            h = {"op": "receive", "channel": item["channel"]}
            if item.get("label"):
                h["label"] = item["label"]
            hints.append(h)
        return hints

    @staticmethod
    def _op_hint(op_type: str, op_args: dict) -> dict:
        return {"op": op_type, **op_args}

    # --- Public on_* methods ---

    def on_acquire(self, agent_id: str, resource_id: str) -> bool:
        return self._try_match(agent_id, "acquire", {"resource": resource_id})

    def on_release(self, agent_id: str, resource_id: str) -> bool:
        return self._try_match(agent_id, "release", {"resource": resource_id})

    def on_send(self, agent_id: str, channel_id: str, label: str) -> bool:
        return self._try_match(agent_id, "send", {"channel": channel_id, "label": label})

    def on_receive(self, agent_id: str, channel_id: str, label: str | None = None) -> bool:
        args: dict = {"channel": channel_id}
        if label is not None:
            args["label"] = label
        return self._try_match(agent_id, "receive", args)

    # --- Core matching ---

    def _try_match(self, agent_id: str, op_type: str, op_args: dict) -> bool:
        # NOTE: Caller must hold a per-agent lock — see class docstring.
        if agent_id not in self._current:
            logger.warning("StateTracker: unknown agent '%s'", agent_id)
            return False

        # 0. Resolve ambiguous candidates from nondeterministic skip paths
        if agent_id in self._candidates:
            return self._resolve_candidates(agent_id, op_type, op_args)

        # 1. Check pending ops from a compound action
        if agent_id in self._pending:
            pending = self._pending[agent_id]
            for i, (ptype, pargs) in enumerate(pending["remaining"]):
                if self._ops_match(ptype, pargs, op_type, op_args):
                    pending["remaining"].pop(i)
                    if not pending["remaining"]:
                        next_state = pending["next_state"]
                        increment = pending.get("increment")
                        del self._pending[agent_id]
                        if increment:
                            self._apply_increment({"increment": increment})
                        self._advance(agent_id, next_state)
                    return True
            # Pending exists but op doesn't match any remaining op
            self._record_violation(agent_id, op_type, op_args)
            return False

        # 2. Check current state actions (with guard filtering)
        state_id = self._current[agent_id]
        actions = self._state_map.get(agent_id, {}).get(state_id, [])
        actions = self._filter_actions_by_guard(actions)

        # 2a. Prefer clean matches (no remaining ops) over compound matches
        best_compound: tuple[dict, list] | None = None
        for action in actions:
            if self._action_has_op(action, op_type, op_args):
                remaining = self._collect_remaining_ops(action, op_type, op_args)
                if not remaining:
                    self._apply_increment(action)
                    self._advance(agent_id, action["next_state"])
                    return True
                if best_compound is None:
                    best_compound = (action, remaining)

        # 2b. Look through skip actions (resolve nondeterministic skip states)
        # Collect ALL matching skip paths to handle ambiguous cases where
        # multiple targets share the same first observable operation.
        # Checked BEFORE committing to a compound match, so skip-path clean
        # matches are preferred over compound matches with pending ops.
        skip_matches: list[dict] = []
        for action in actions:
            if self._is_skip_action(action):
                target = self._resolve_skip_chain(agent_id, action["next_state"])
                target_actions = self._state_map.get(agent_id, {}).get(target, [])
                for target_action in target_actions:
                    if self._action_has_op(target_action, op_type, op_args):
                        remaining = self._collect_remaining_ops(
                            target_action, op_type, op_args)
                        skip_matches.append({
                            "state": target,
                            "remaining": remaining,
                            "next_state": target_action["next_state"],
                            "increment": target_action.get("increment"),
                        })

        if len(skip_matches) == 1:
            # Single match — commit immediately
            match = skip_matches[0]
            self._current[agent_id] = match["state"]
            if match["remaining"]:
                self._pending[agent_id] = {
                    "remaining": match["remaining"],
                    "next_state": match["next_state"],
                    "increment": match.get("increment"),
                }
            else:
                if match.get("increment"):
                    self._apply_increment({"increment": match["increment"]})
                self._advance(agent_id, match["next_state"])
            return True
        elif len(skip_matches) > 1:
            # Multiple matches — defer via NFA-style candidate tracking
            self._candidates[agent_id] = skip_matches
            return True

        # 2c. Fall back to compound match (with pending ops)
        if best_compound is not None:
            action, remaining = best_compound
            self._pending[agent_id] = {
                "remaining": remaining,
                "next_state": action["next_state"],
                "increment": action.get("increment"),
            }
            return True

        # 3. No match → violation
        self._record_violation(agent_id, op_type, op_args)
        return False

    def _resolve_candidates(self, agent_id: str, op_type: str,
                            op_args: dict) -> bool:
        """Resolve ambiguous skip-path candidates with an incoming operation.

        When multiple skip paths share the same first observable operation,
        candidates are tracked NFA-style until subsequent operations
        disambiguate which path the agent actually took.
        """
        candidates = self._candidates[agent_id]
        surviving: list[dict] = []

        for cand in candidates:
            if cand["remaining"]:
                # Compound candidate: check if op matches any remaining op
                for i, (ptype, pargs) in enumerate(cand["remaining"]):
                    if self._ops_match(ptype, pargs, op_type, op_args):
                        new_remaining = list(cand["remaining"])
                        new_remaining.pop(i)
                        surviving.append({
                            "state": cand["state"],
                            "remaining": new_remaining,
                            "next_state": cand["next_state"],
                            "increment": cand.get("increment"),
                        })
                        break
            else:
                # Clean candidate: already fully consumed. Check if op
                # matches from the (conceptually transitioned) next state.
                # Apply candidate's increment before moving on.
                if cand.get("increment"):
                    self._apply_increment({"increment": cand["increment"]})
                resolved = self._resolve_skip_chain(
                    agent_id, cand["next_state"])
                next_actions = self._state_map.get(
                    agent_id, {}).get(resolved, [])
                for action in next_actions:
                    if self._action_has_op(action, op_type, op_args):
                        remaining = self._collect_remaining_ops(
                            action, op_type, op_args)
                        surviving.append({
                            "state": resolved,
                            "remaining": remaining,
                            "next_state": action["next_state"],
                            "increment": action.get("increment"),
                        })
                        break

        if not surviving:
            del self._candidates[agent_id]
            self._record_violation(agent_id, op_type, op_args)
            return False

        if len(surviving) == 1:
            # Unambiguous — commit to this path
            del self._candidates[agent_id]
            match = surviving[0]
            self._current[agent_id] = match["state"]
            if match["remaining"]:
                self._pending[agent_id] = {
                    "remaining": match["remaining"],
                    "next_state": match["next_state"],
                    "increment": match.get("increment"),
                }
            else:
                if match.get("increment"):
                    self._apply_increment({"increment": match["increment"]})
                self._advance(agent_id, match["next_state"])
            return True

        # Still ambiguous — keep tracking
        self._candidates[agent_id] = surviving
        return True

    def _ops_match(self, ptype: str, pargs: dict,
                   op_type: str, op_args: dict) -> bool:
        """Check if a pending op matches the incoming op."""
        if ptype != op_type:
            return False
        if op_type in ("acquire", "release"):
            return pargs.get("resource") == op_args.get("resource")
        if op_type == "send":
            return (pargs.get("channel") == op_args.get("channel")
                    and pargs.get("label") == op_args.get("label"))
        if op_type == "receive":
            if pargs.get("channel") != op_args.get("channel"):
                return False
            if "label" in pargs and "label" in op_args:
                return pargs["label"] == op_args["label"]
            return True
        return False

    # --- Action matching helpers ---

    def _action_has_op(self, action: dict, op_type: str, op_args: dict) -> bool:
        if op_type == "acquire":
            return self._match_resource(action.get("acquire"), op_args.get("resource"))
        if op_type == "release":
            return self._match_resource(action.get("release"), op_args.get("resource"))
        if op_type == "send":
            return self._match_send(action.get("send"), op_args)
        if op_type == "receive":
            return self._match_receive(action.get("receive"), op_args)
        return False

    @staticmethod
    def _match_resource(field, resource_id: str | None) -> bool:
        if field is None or resource_id is None:
            return False
        if isinstance(field, str):
            return field == resource_id
        if isinstance(field, list):
            return resource_id in field
        return False

    @staticmethod
    def _match_send(field, op_args: dict) -> bool:
        if field is None:
            return False
        items = [field] if isinstance(field, dict) else field
        for item in items:
            if (item.get("channel") == op_args.get("channel")
                    and item.get("label") == op_args.get("label")):
                return True
        return False

    @staticmethod
    def _match_receive(field, op_args: dict) -> bool:
        if field is None:
            return False
        items = [field] if isinstance(field, dict) else field
        for item in items:
            if item.get("channel") != op_args.get("channel"):
                continue
            action_label = item.get("label")
            caller_label = op_args.get("label")
            if action_label and caller_label and action_label != caller_label:
                continue
            return True
        return False

    # --- Remaining ops collection ---

    def _collect_remaining_ops(self, action: dict, matched_type: str,
                               matched_args: dict) -> list[tuple[str, dict]]:
        """Collect all coord ops in the action EXCEPT the matched one."""
        remaining: list[tuple[str, dict]] = []
        matched_once = False

        for res in self._normalize_resource(action.get("acquire")):
            if (not matched_once and matched_type == "acquire"
                    and res == matched_args.get("resource")):
                matched_once = True
                continue
            remaining.append(("acquire", {"resource": res}))

        for res in self._normalize_resource(action.get("release")):
            if (not matched_once and matched_type == "release"
                    and res == matched_args.get("resource")):
                matched_once = True
                continue
            remaining.append(("release", {"resource": res}))

        for item in self._normalize_send_receive(action.get("send")):
            if (not matched_once and matched_type == "send"
                    and item.get("channel") == matched_args.get("channel")
                    and item.get("label") == matched_args.get("label")):
                matched_once = True
                continue
            remaining.append(("send", {"channel": item["channel"], "label": item["label"]}))

        for item in self._normalize_send_receive(action.get("receive")):
            args: dict = {"channel": item["channel"]}
            if "label" in item:
                args["label"] = item["label"]
            if not matched_once and matched_type == "receive":
                if item.get("channel") == matched_args.get("channel"):
                    action_label = item.get("label")
                    caller_label = matched_args.get("label")
                    if not (action_label and caller_label
                            and action_label != caller_label):
                        matched_once = True
                        continue
            remaining.append(("receive", args))

        return remaining

    @staticmethod
    def _normalize_resource(field) -> list[str]:
        if field is None:
            return []
        if isinstance(field, str):
            return [field]
        return list(field)

    @staticmethod
    def _normalize_send_receive(field) -> list[dict]:
        if field is None:
            return []
        if isinstance(field, dict):
            return [field]
        return list(field)

    # --- State advancement ---

    def _advance(self, agent_id: str, next_state: str):
        self._current[agent_id] = next_state
        # The agent just landed on a coordination position via a real op; clear any
        # business phase. _auto_advance re-sets it if this transition steps through a
        # (no-op) business state on the way to the next coordination checkpoint.
        self._current_phases.pop(agent_id, None)
        self._auto_advance(agent_id)

    def _auto_advance(self, agent_id: str):
        """Auto-advance through skip states (no coord ops, exactly one action)."""
        visited: set[str] = set()
        while True:
            state_id = self._current[agent_id]
            if state_id in visited:
                logger.error("Malformed states.json: skip-chain cycle detected at %s for %s", state_id, agent_id)
                break
            visited.add(state_id)
            actions = self._state_map.get(agent_id, {}).get(state_id, [])
            if not actions:
                break
            filtered = self._filter_actions_by_guard(actions)
            if len(filtered) != 1:
                break
            if not self._is_skip_action(filtered[0]):
                break
            self._apply_increment(filtered[0])
            # state_id is a no-op BUSINESS state the agent is passing through —
            # record it as the agent's current business phase (observability only).
            self._current_phases[agent_id] = state_id
            self._current[agent_id] = filtered[0]["next_state"]

    def _resolve_skip_chain(self, agent_id: str, state_id: str) -> str:
        """Follow single-skip actions without mutating state."""
        visited: set[str] = set()
        while True:
            if state_id in visited:
                logger.error("Malformed states.json: skip-chain cycle detected at %s for %s", state_id, agent_id)
                break
            visited.add(state_id)
            actions = self._state_map.get(agent_id, {}).get(state_id, [])
            if not actions:
                break
            filtered = self._filter_actions_by_guard(actions)
            if len(filtered) != 1:
                break
            if not self._is_skip_action(filtered[0]):
                break
            state_id = filtered[0]["next_state"]
        return state_id

    @staticmethod
    def _is_skip_action(action: dict) -> bool:
        """True if action has no coordination operations."""
        return not any(action.get(k) for k in ("acquire", "release", "send", "receive"))

    # --- Violation recording ---

    def _record_violation(self, agent_id: str, op_type: str, op_args: dict):
        state_id = self._current[agent_id]
        actions = self._state_map.get(agent_id, {}).get(state_id, [])
        self._violations.append(StateViolation(
            agent=agent_id,
            current_state=state_id,
            operation=op_type,
            args=op_args,
            valid_actions=list(actions),
            timestamp=time.time(),
        ))
