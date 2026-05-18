"""Parameterized shared-codebase development simulation (scenarios 1E/1M/1H).

Resource model: each developer needs exclusive locks on the specific
code modules they modify (per-module mutex), not a single coarse repo lock.
The module set per agent is derived from CommitStep.modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._base import ToolResult
from .sim_base import SimContext


@dataclass
class DesignStep:
    """A feature design step."""

    agent_id: str
    feature: str


@dataclass
class ImplementStep:
    """A code implementation step."""

    agent_id: str
    feature: str


@dataclass
class CommitStep:
    """A commit step for one or more modules."""

    agent_id: str
    modules: list[str]


@dataclass
class TestStep:
    """A local test run step."""

    agent_id: str
    feature: str


class CodingSim(SimContext):
    """Simulation for shared-codebase development with per-module locking.

    Each developer touches a specific set of code modules.  Only
    ``commit_changes`` requires the caller to hold **all** of their module
    locks (derived from the ``CommitStep`` configuration).  This enables
    ring-shaped circular-wait deadlock detection when modules overlap between
    developers.

    Args:
        design_steps: Feature design steps (no resource required).
        implement_steps: Code implementation steps (need module locks).
        commit_steps: Commit steps (need module locks).
        test_steps: Local test run steps (no resource required).
        resources: List of shared module names (each modeled as a mutex).
    """

    def __init__(
        self,
        design_steps: list[DesignStep],
        implement_steps: list[ImplementStep],
        commit_steps: list[CommitStep],
        test_steps: list[TestStep],
        resources: list[str],
    ) -> None:
        super().__init__()

        self._design_steps = {f"{s.agent_id}_{s.feature}": s for s in design_steps}
        self._implement_steps = {f"{s.agent_id}_{s.feature}": s for s in implement_steps}
        self._commit_steps = {f"{s.agent_id}_{'_'.join(sorted(s.modules))}": s for s in commit_steps}
        self._test_steps = {f"{s.agent_id}_{s.feature}": s for s in test_steps}

        self._design_done: dict[str, bool] = {k: False for k in self._design_steps}
        self._implement_done: dict[str, bool] = {k: False for k in self._implement_steps}
        self._commit_done: dict[str, bool] = {k: False for k in self._commit_steps}
        self._test_done: dict[str, bool] = {k: False for k in self._test_steps}

        # Per-agent module mapping (agent_id → list of module locks needed)
        self._agent_modules: dict[str, list[str]] = {
            s.agent_id: list(s.modules) for s in commit_steps
        }

        for res in resources:
            self.init_resource(res)

    # -- Decision tools (probabilistic failure for either/or branches) --
    # run_local_tests drives the pass/fail either/or branch at the *_test state.
    # On failure the agent retries: re-implement → re-acquire locks → re-commit → re-test.
    _DECISION_TOOLS: dict[str, float] = {
        "run_local_tests": 0.3,
    }

    # resource_requirements() is handled by SimContext.load_from_metadata()
    # via metadata.json tool_resource_map / agent_resources.

    _TOOL_DELAYS: dict[str, tuple[float, float]] = {
        "design_feature": (0.5, 1.5),
        "implement_code": (1.0, 3.0),
        "commit_changes": (0.5, 1.0),
        "run_local_tests": (1.5, 4.0),
    }

    def tool_delay(self, tool_name: str, **kwargs: Any) -> tuple[float, float]:
        return self._TOOL_DELAYS.get(tool_name, (0.0, 0.0))

    # -- Tool implementations --

    def design_feature(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Design a feature. No resource required."""
        feature = self._get_param(kwargs, "feature_name", "feature")

        key = self._match_key(self._design_done, agent_id, feature)
        if key in self._design_done:
            self._design_done[key] = True

        result = {"feature": feature, "status": "designed", "agent": agent_id}
        self.log_event(agent_id, "design_feature", {"feature": feature},
                       success=True, result=result)
        return ToolResult(tool_name="design_feature", success=True,
                          data=result, message=f"Designed feature: {feature}")

    def implement_code(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Implement code locally. No resource required."""
        feature = self._get_param(kwargs, "feature_name", "feature")

        key = self._match_key(self._implement_done, agent_id, feature)
        if key in self._implement_done:
            self._implement_done[key] = True

        result = {"feature": feature, "status": "implemented", "agent": agent_id}
        self.log_event(agent_id, "implement_code", {"feature": feature},
                       success=True, result=result)
        return ToolResult(tool_name="implement_code", success=True,
                          data=result, message=f"Implemented: {feature}")

    def commit_changes(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Commit changes. Requires holding all module locks for this agent."""
        raw_modules = kwargs.get("modules", [])
        modules = self._parse_list(raw_modules) if raw_modules else []
        if not modules:
            # Prefer metadata-driven agent_resources; fall back to constructor arg
            modules = (self._agent_resources.get(agent_id)
                       or self._agent_modules.get(agent_id, []))
        modules_str = ", ".join(modules) if modules else "all"

        key = f"{agent_id}_{'_'.join(sorted(modules))}" if modules else f"{agent_id}_all"
        if key in self._commit_done:
            self._commit_done[key] = True

        result = {"modules": modules, "status": "committed", "agent": agent_id}
        self.log_event(agent_id, "commit_changes", {"modules": modules},
                       success=True, result=result)
        return ToolResult(tool_name="commit_changes", success=True,
                          data=result, message=f"Committed: {modules_str}")

    def run_local_tests(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Run local tests. No resource required (read-only)."""
        feature = self._get_param(kwargs, "feature_name", "feature")

        key = self._match_key(self._test_done, agent_id, feature)

        if self.should_fail("run_local_tests", agent_id):
            result = {"feature": feature, "status": "tests_failed", "agent": agent_id}
            self.log_event(agent_id, "run_local_tests", {"feature": feature},
                           success=False, result=result)
            return ToolResult(tool_name="run_local_tests", success=False,
                              data=result, message=f"Tests FAILED: {feature}")

        # Only mark done when tests actually pass (agent may retry on failure)
        if key in self._test_done:
            self._test_done[key] = True

        result = {"feature": feature, "status": "tests passed", "agent": agent_id}
        self.log_event(agent_id, "run_local_tests", {"feature": feature},
                       success=True, result=result)
        return ToolResult(tool_name="run_local_tests", success=True,
                          data=result, message=f"Tests passed: {feature}")

    # -- SimContext interface --

    def make_tools(self) -> dict[str, Any]:
        return {
            "design_feature": self.design_feature,
            "implement_code": self.implement_code,
            "commit_changes": self.commit_changes,
            "run_local_tests": self.run_local_tests,
        }

    def is_complete(self) -> bool:
        return (all(self._design_done.values()) and
                all(self._implement_done.values()) and
                all(self._commit_done.values()) and
                all(self._test_done.values()))

    @property
    def progress(self) -> dict[str, Any]:
        return {
            "designs": dict(self._design_done),
            "implementations": dict(self._implement_done),
            "commits": dict(self._commit_done),
            "tests": dict(self._test_done),
            "all_complete": self.is_complete(),
        }
