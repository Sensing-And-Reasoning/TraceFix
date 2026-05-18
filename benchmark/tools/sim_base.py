"""Domain-agnostic simulation primitives for benchmark tasks."""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ._base import ToolResult


# -- Difficulty presets --

DIFFICULTY_RATES: dict[int, float] = {
    0: 0.0,       # easy — no injected failures
    1: 0.3,       # medium
    2: 0.6,       # hard
    3: 0.9,       # nightmare
}


# -- Failure injection data types --

@dataclass
class FailureSpec:
    """Specifies when a tool invocation should return failure.

    Args:
        tool_name: The sim tool to inject failure into.
        agent_id: Restrict to this agent (None = any agent).
        call_index: Fail on the Nth call (0-based). None = use probability.
        probability: Probability of failure per call (when call_index is None).
    """

    tool_name: str
    agent_id: str | None = None
    call_index: int | None = None
    probability: float = 1.0


@dataclass
class FailureScenario:
    """A named collection of failure specs for a task sim.

    Args:
        name: Scenario identifier (e.g., "metro_fail").
        failures: List of FailureSpec rules to activate.
        description: Human-readable description.
    """

    name: str
    failures: list[FailureSpec] = field(default_factory=list)
    description: str = ""


@dataclass
class Violation:
    """A detected coordination violation."""

    timestamp: float
    agent: str
    tool: str
    violation_type: str
    message: str


@dataclass
class SimEvent:
    """A logged tool invocation with outcome."""

    timestamp: float
    agent: str
    tool: str
    args: dict[str, Any]
    success: bool
    result: dict[str, Any]
    violations: list[Violation] = field(default_factory=list)


class SimContext(ABC):
    """Base class for simulation environments.

    Provides resource management (modeled after tracefix.runtime.enforcement/store.py's LockStore)
    and event/violation logging.  Subclasses implement domain-specific tool
    methods and completion logic.
    """

    # Subclasses define available failure scenarios (class-level)
    _FAILURE_SCENARIOS: dict[str, FailureScenario] = {}

    # Subclasses define decision-point tools with default fail probability.
    # These are tools whose result determines an either/or branch in PlusCal
    # (e.g., review → approve/revise, test → pass/fail).
    _DECISION_TOOLS: dict[str, float] = {}

    def __init__(
        self,
        decision_fail_rate: float | None = None,
        *,
        delay_multiplier: float = 1.0,
        seed: int | None = None,
    ) -> None:
        self._resources: dict[str, str | None] = {}  # resource_id → holder or None
        self._events: list[SimEvent] = []
        self._violations: list[Violation] = []
        # Concurrent resource usage tracking (independent of locks)
        self._in_use: dict[str, list[tuple[str, str]]] = {}  # resource_id → [(agent_id, tool_name)]
        self._resource_capacity: dict[str, int] = {}  # resource_id → max concurrent users
        # Failure injection state
        self._failure_specs: list[FailureSpec] = []
        self._call_counts: dict[str, int] = {}  # "tool:agent" → count
        self._optional_items: set[str] = set()  # progress keys that may be skipped
        # Delay and RNG state
        self._delay_multiplier = delay_multiplier
        self._seed = seed
        self._agent_rngs: dict[str, random.Random] = {}

        # Metadata-driven resource-tool bindings (populated by load_from_metadata)
        self._tool_resource_map: dict[str, Any] = {}
        self._agent_resources: dict[str, list[str]] = {}

        # Auto-populate failure specs from decision tools
        if decision_fail_rate is not None and self._DECISION_TOOLS:
            for tool_name, default_prob in self._DECISION_TOOLS.items():
                prob = decision_fail_rate if decision_fail_rate > 0 else default_prob
                self._failure_specs.append(
                    FailureSpec(tool_name=tool_name, probability=prob)
                )

    # -- Resource management (sim-internal, for Category D acquire/release tools) --

    def init_resource(self, resource_id: str, capacity: int = 1) -> None:
        """Register a resource in the free state.

        Args:
            resource_id: The resource identifier.
            capacity: Max concurrent users (default 1 = exclusive).
        """
        self._resources[resource_id] = None
        self._resource_capacity[resource_id] = capacity

    def try_acquire(self, resource_id: str, agent_id: str) -> bool:
        """Atomically acquire a resource.  Returns True on success."""
        if resource_id not in self._resources:
            return False
        if self._resources[resource_id] is None:
            self._resources[resource_id] = agent_id
            return True
        return False

    def release(self, resource_id: str, agent_id: str) -> bool:
        """Release a resource.  Returns True if the agent held it."""
        if resource_id not in self._resources:
            return False
        if self._resources[resource_id] == agent_id:
            self._resources[resource_id] = None
            return True
        return False

    def holder_of(self, resource_id: str) -> str | None:
        """Return the current holder of a resource (sim-internal state only)."""
        return self._resources.get(resource_id)

    def agent_holds(self, agent_id: str, resource_id: str) -> bool:
        """Check sim-internal resource state (for Category D acquire/release tools)."""
        return self._resources.get(resource_id) == agent_id

    def resource_exists(self, resource_id: str) -> bool:
        """Check if a resource has been initialized."""
        return resource_id in self._resources

    # -- Concurrent resource usage tracking --

    def load_from_metadata(self, metadata: dict) -> None:
        """Load resource-tool bindings from a metadata.json dict.

        Reads two optional keys:
        - ``agent_resources``: maps agent_id → list of resource IDs that agent
          owns (e.g. which modules a developer commits to).
        - ``tool_resource_map``: maps tool_name → resource requirement spec.
          Spec can be:
          - A list of resource IDs (static, same for all agents).
          - ``"@agent_resources"`` (dynamic, looks up per-agent from
            ``agent_resources``).

        After calling this, ``resource_requirements()`` uses the loaded
        mappings instead of returning ``[]``.
        """
        self._agent_resources = {
            k: list(v) for k, v in metadata.get("agent_resources", {}).items()
        }
        self._tool_resource_map = dict(metadata.get("tool_resource_map", {}))
        for res_id, cap in metadata.get("resource_capacity", {}).items():
            self._resource_capacity[res_id] = cap

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        """Return resource IDs needed by *tool_name*.

        If ``load_from_metadata()`` has been called, uses the metadata-driven
        ``tool_resource_map``.  Supports:
        - Static list: ``{"compile_code": ["BUILD_SERVER"]}``
        - Per-agent dynamic: ``{"commit_changes": "@agent_resources"}``

        Subclasses may still override for cases not expressible in JSON
        (e.g. resources determined by a non-agent-id runtime parameter).
        """
        if not self._tool_resource_map:
            return []
        mapping = self._tool_resource_map.get(tool_name)
        if mapping is None:
            return []
        if mapping == "@agent_resources":
            agent_id = kwargs.get("agent_id", "")
            return list(self._agent_resources.get(agent_id, []))
        if isinstance(mapping, list):
            return list(mapping)
        return []

    def tool_delay(self, tool_name: str, **kwargs: Any) -> tuple[float, float]:
        """Return ``(min_delay, max_delay)`` for *tool_name*.

        Override in subclasses to simulate realistic business-logic
        processing times (compile duration, test duration, etc.).
        Default is ``(0, 0)`` (instant).
        """
        return (0.0, 0.0)

    def begin_resource_use(
        self, agent_id: str, tool_name: str, resources: list[str]
    ) -> list[Violation]:
        """Mark *resources* as in use by *agent_id*.

        If the resource's capacity is exceeded by other agents, a
        ``concurrent_resource_use`` violation is logged.  Returns the list
        of violations (may be empty).
        """
        violations: list[Violation] = []
        for res in resources:
            if res not in self._resource_capacity:
                continue  # skip resources not initialized in this sim
            users = self._in_use.setdefault(res, [])
            # Count how many *other* agents are currently using this resource
            other_users = [(a, t) for a, t in users if a != agent_id]
            capacity = self._resource_capacity[res]
            if len(other_users) >= capacity:
                others_desc = ", ".join(
                    f"{a} (via {t})" for a, t in other_users
                )
                v = self.log_violation(
                    agent_id,
                    tool_name,
                    "concurrent_resource_use",
                    f"{agent_id} needs {res} for {tool_name} but "
                    f"capacity {capacity} exhausted by: {others_desc}",
                )
                violations.append(v)
            users.append((agent_id, tool_name))
        return violations

    def end_resource_use(self, agent_id: str, resources: list[str]) -> None:
        """Clear in-use markers after *agent_id*'s operation completes."""
        for res in resources:
            users = self._in_use.get(res, [])
            # Remove the first matching entry for this agent
            for i, (a, _t) in enumerate(users):
                if a == agent_id:
                    users.pop(i)
                    break

    # -- Logging --

    def log_violation(
        self, agent: str, tool: str, violation_type: str, message: str
    ) -> Violation:
        """Record a violation and return it."""
        v = Violation(
            timestamp=time.monotonic(),
            agent=agent,
            tool=tool,
            violation_type=violation_type,
            message=message,
        )
        self._violations.append(v)
        return v

    def log_event(
        self,
        agent: str,
        tool: str,
        args: dict[str, Any],
        success: bool,
        result: dict[str, Any],
        violations: list[Violation] | None = None,
    ) -> SimEvent:
        """Record a tool invocation event."""
        ev = SimEvent(
            timestamp=time.monotonic(),
            agent=agent,
            tool=tool,
            args=args,
            success=success,
            result=result,
            violations=violations or [],
        )
        self._events.append(ev)
        return ev

    # -- Failure injection --

    def set_decision_fail_rate(self, rate: float) -> None:
        """Configure probabilistic failure for decision-point tools.

        Call after construction to inject failure into tools listed in
        ``_DECISION_TOOLS``.  If *rate* > 0, all decision tools use that
        probability; if *rate* == 0 (or negative), each tool uses its
        class-defined default probability.
        """
        if not self._DECISION_TOOLS:
            return
        for tool_name, default_prob in self._DECISION_TOOLS.items():
            prob = rate if rate > 0 else default_prob
            self._failure_specs.append(
                FailureSpec(tool_name=tool_name, probability=prob)
            )

    def set_difficulty(self, level: int) -> None:
        """Apply a difficulty preset (0=easy, 1=medium, 2=hard, 3=nightmare).

        Maps to a ``decision_fail_rate`` via ``DIFFICULTY_RATES``.
        """
        rate = DIFFICULTY_RATES.get(level)
        if rate is None:
            raise ValueError(
                f"Unknown difficulty {level}. "
                f"Available: {', '.join(str(k) for k in DIFFICULTY_RATES)}")
        if rate > 0:
            self.set_decision_fail_rate(rate)

    def set_scenario_depth(self, depth: int) -> None:
        """Configure deterministic retry depth for decision-point tools.

        Each decision tool fails on the first *depth* calls (per agent),
        then succeeds.
        """
        if not self._DECISION_TOOLS:
            return
        self._failure_specs = []  # clear any prior specs
        for tool_name in self._DECISION_TOOLS:
            for i in range(depth):
                self._failure_specs.append(
                    FailureSpec(tool_name=tool_name, call_index=i)
                )

    def configure_scenario(self, name: str) -> None:
        """Activate a named failure scenario defined in ``_FAILURE_SCENARIOS``."""
        scenario = self._FAILURE_SCENARIOS.get(name)
        if scenario is None:
            available = ", ".join(self._FAILURE_SCENARIOS) or "(none)"
            raise ValueError(
                f"Unknown failure scenario '{name}'. Available: {available}")
        self._failure_specs = list(scenario.failures)

    def should_fail(self, tool_name: str, agent_id: str) -> bool:
        """Check whether this tool call should be injected with failure.

        Increments per-tool-per-agent call count and checks against active
        FailureSpec rules.  Returns True if the call should fail.
        """
        key = f"{tool_name}:{agent_id}"
        idx = self._call_counts.get(key, 0)
        self._call_counts[key] = idx + 1

        for spec in self._failure_specs:
            if spec.tool_name != tool_name:
                continue
            if spec.agent_id is not None and spec.agent_id != agent_id:
                continue
            if spec.call_index is not None:
                if idx == spec.call_index:
                    return True
            else:
                if self._rng_for(agent_id).random() < spec.probability:
                    return True
        return False

    def _check_all_done(self, tracker: dict[str, bool]) -> bool:
        """Like ``all(tracker.values())`` but skips keys in ``_optional_items``."""
        return all(
            v for k, v in tracker.items() if k not in self._optional_items
        )

    def _rng_for(self, agent_id: str) -> random.Random:
        """Return a per-agent Random instance (seeded deterministically when ``_seed`` is set)."""
        if agent_id not in self._agent_rngs:
            if self._seed is not None:
                derived = self._seed ^ hash(agent_id)
                self._agent_rngs[agent_id] = random.Random(derived)
            else:
                self._agent_rngs[agent_id] = random.Random()
        return self._agent_rngs[agent_id]

    # -- Parameter helpers --

    @staticmethod
    def _normalize(s: str) -> str:
        """Normalize a string for fuzzy key matching.

        Converts to lowercase, replaces whitespace/hyphens with underscores,
        and strips leading/trailing underscores.
        """
        return s.lower().replace(" ", "_").replace("-", "_").strip("_")

    @staticmethod
    def _get_param(kwargs: dict[str, Any], *names: str, default: str = "unknown") -> str:
        """Extract a parameter trying multiple names (for tools.json ↔ sim alignment)."""
        for name in names:
            val = kwargs.get(name)
            if val is not None:
                return val
        return default

    @staticmethod
    def _parse_list(raw: Any, sep: str = ",") -> list[str]:
        """Parse a value that may be a string or list into a list of strings."""
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str) and raw:
            return [item.strip() for item in raw.split(sep) if item.strip()]
        return []

    def _match_key(self, tracker: dict[str, bool], agent_id: str, value: str) -> str:
        """Find the best matching key in a progress tracker.

        Tries exact match first, then normalized match, then startswith,
        then token overlap (for cases like ``sec_intro_methods`` vs
        ``intro-methods connection``).
        """
        exact = f"{agent_id}_{value}"
        if exact in tracker:
            return exact

        norm_val = self._normalize(value)
        best_key = None
        best_score = 0.0

        for key in tracker:
            if not key.startswith(f"{agent_id}_"):
                continue
            suffix = key[len(agent_id) + 1:]
            norm_suffix = self._normalize(suffix)

            # Exact normalized match
            if norm_suffix == norm_val:
                return key

            # Prefix containment (one starts with the other)
            if norm_val.startswith(norm_suffix) or norm_suffix.startswith(norm_val):
                return key

            # Token overlap — handles prefix mismatches like sec_ or section_
            val_tokens = set(norm_val.split("_"))
            key_tokens = set(norm_suffix.split("_"))
            common = val_tokens & key_tokens
            if common:
                smaller = min(len(val_tokens), len(key_tokens))
                score = len(common) / smaller
                if score >= 0.6 and score > best_score:
                    best_score = score
                    best_key = key

        return best_key or exact

    def _mark_done(self, done_dict: dict[str, bool], agent_id: str, value: str) -> bool:
        """Mark a tracker item as done.

        Matching strategy (first match wins):
        1. Exact key ``{agent_id}_{value}``.
        2. Case-insensitive normalized matching (lowercase, spaces/hyphens →
           underscores).
        3. Token overlap: if the value shares significant tokens with a key's
           suffix (e.g. ``user_authentication`` ↔ ``user_auth``), pick the
           best-scoring unmatched key for this agent.
        4. Agent-prefix fallback: first unmatched key starting with
           ``{agent_id}_``.  This handles LLM agents that pass entirely
           different parameter values than the sim checklist expects.

        Returns ``True`` if a matching key was found.
        """
        exact = f"{agent_id}_{value}"
        if exact in done_dict:
            done_dict[exact] = True
            return True
        norm = self._normalize(exact)
        for k in done_dict:
            if self._normalize(k) == norm:
                done_dict[k] = True
                return True

        # -- Token overlap matching --
        prefix = f"{agent_id}_"
        val_tokens = set(self._normalize(value).split("_"))
        val_tokens.discard("")
        best_score, best_key = 0.0, None
        for k in done_dict:
            if done_dict[k] or not k.startswith(prefix):
                continue
            key_suffix = k[len(prefix):]
            key_tokens = set(self._normalize(key_suffix).split("_"))
            key_tokens.discard("")
            common = val_tokens & key_tokens
            if common:
                smaller = min(len(val_tokens), len(key_tokens))
                score = len(common) / smaller
                if score > best_score:
                    best_score = score
                    best_key = k
        if best_key and best_score >= 0.5:
            done_dict[best_key] = True
            return True

        # -- Agent-prefix fallback: first unmatched entry for this agent --
        for k in done_dict:
            if not done_dict[k] and k.startswith(prefix):
                done_dict[k] = True
                return True
        return False

    # -- Read-only properties --

    @property
    def events(self) -> list[SimEvent]:
        return list(self._events)

    @property
    def violations(self) -> list[Violation]:
        return list(self._violations)

    @property
    def has_violations(self) -> bool:
        return len(self._violations) > 0

    # -- Abstract interface --

    @abstractmethod
    def make_tools(self) -> dict[str, Any]:
        """Return a ``{tool_name: callable}`` dict for sim-mode dispatch."""

    @abstractmethod
    def is_complete(self) -> bool:
        """Return True when the simulation goal is fully achieved."""

    @abstractmethod
    def progress(self) -> dict[str, Any]:
        """Return a dict describing current progress toward the goal."""
