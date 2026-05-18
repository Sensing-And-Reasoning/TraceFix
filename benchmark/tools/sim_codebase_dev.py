"""Parameterized codebase development simulation (scenarios 6E/6M/6H)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._base import ToolResult
from .sim_base import SimContext


@dataclass
class ImplementStep:
    """A feature implementation step."""

    agent_id: str
    feature: str


@dataclass
class WriteTestsStep:
    """A test writing step."""

    agent_id: str
    component: str


@dataclass
class CodeReviewStep:
    """A code review step."""

    agent_id: str
    target: str


@dataclass
class RunTestsStep:
    """A test execution step."""

    agent_id: str
    suite: str


@dataclass
class MergeStep:
    """A code merge step."""

    agent_id: str
    branch: str


@dataclass
class DeployStep:
    """A service deployment step."""

    agent_id: str
    service: str


@dataclass
class RollbackStep:
    """A service rollback step."""

    agent_id: str
    service: str


@dataclass
class ValidateStagingStep:
    """A staging validation step."""

    agent_id: str
    service: str


class CodebaseDevSim(SimContext):
    """Simulation for codebase development with build and staging infrastructure.

    Tracks per-agent progress through implementation, testing, merge,
    and deployment phases.  Detects violations such as missing resource
    holds for repo, build_server, test_env, and staging_env.

    Args:
        implement_steps: Feature implementation steps (need repo).
        write_tests_steps: Test writing steps (need test_env).
        code_review_steps: Code review steps (no resource).
        run_tests_steps: Test execution steps (need build_server).
        merge_steps: Code merge steps (need repo).
        deploy_steps: Service deployment steps (need staging_env).
        rollback_steps: Service rollback steps (need staging_env).
        validate_staging_steps: Staging validation steps (need staging_env).
        resources: List of shared resource names.
    """

    def __init__(
        self,
        implement_steps: list[ImplementStep] | None = None,
        write_tests_steps: list[WriteTestsStep] | None = None,
        code_review_steps: list[CodeReviewStep] | None = None,
        run_tests_steps: list[RunTestsStep] | None = None,
        merge_steps: list[MergeStep] | None = None,
        deploy_steps: list[DeployStep] | None = None,
        rollback_steps: list[RollbackStep] | None = None,
        validate_staging_steps: list[ValidateStagingStep] | None = None,
        resources: list[str] | None = None,
    ) -> None:
        super().__init__()

        self._implement_steps = {f"{s.agent_id}_{s.feature}": s for s in (implement_steps or [])}
        self._write_tests_steps = {f"{s.agent_id}_{s.component}": s for s in (write_tests_steps or [])}
        self._code_review_steps = {f"{s.agent_id}_{s.target}": s for s in (code_review_steps or [])}
        self._run_tests_steps = {f"{s.agent_id}_{s.suite}": s for s in (run_tests_steps or [])}
        self._merge_steps = {f"{s.agent_id}_{s.branch}": s for s in (merge_steps or [])}
        self._deploy_steps = {f"{s.agent_id}_{s.service}": s for s in (deploy_steps or [])}
        self._rollback_steps = {f"{s.agent_id}_{s.service}": s for s in (rollback_steps or [])}
        self._validate_staging_steps = {f"{s.agent_id}_{s.service}": s for s in (validate_staging_steps or [])}

        self._implement_done: dict[str, bool] = {k: False for k in self._implement_steps}
        self._write_tests_done: dict[str, bool] = {k: False for k in self._write_tests_steps}
        self._code_review_done: dict[str, bool] = {k: False for k in self._code_review_steps}
        self._run_tests_done: dict[str, bool] = {k: False for k in self._run_tests_steps}
        self._merge_done: dict[str, bool] = {k: False for k in self._merge_steps}
        self._deploy_done: dict[str, bool] = {k: False for k in self._deploy_steps}
        self._rollback_done: dict[str, bool] = {k: False for k in self._rollback_steps}
        self._validate_staging_done: dict[str, bool] = {k: False for k in self._validate_staging_steps}

        for res in (resources or []):
            self.init_resource(res)

    # -- Decision tools (probabilistic failure for either/or branches) --

    _DECISION_TOOLS: dict[str, float] = {
        "code_review": 0.3,
        "run_tests": 0.3,
        "validate_staging": 0.2,
    }

    # -- Resource requirements --

    _TOOL_RESOURCES: dict[str, list[str]] = {
        "implement_feature": ["REPO"],
        "write_tests": ["TEST_ENV"],
        "code_review": [],
        "run_tests": ["BUILD_SERVER"],
        "merge_code": ["REPO"],
        "deploy_service": ["STAGING_ENV"],
        "rollback_service": ["STAGING_ENV"],
        "validate_staging": ["STAGING_ENV"],
    }

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        return list(self._TOOL_RESOURCES.get(tool_name, []))

    # -- Simulated delays --

    _TOOL_DELAYS: dict[str, tuple[float, float]] = {
        "implement_feature": (1.5, 4.0),
        "write_tests": (1.0, 2.5),
        "code_review": (1.0, 2.0),
        "run_tests": (2.0, 5.0),
        "merge_code": (0.5, 1.0),
        "deploy_service": (1.0, 3.0),
        "rollback_service": (0.5, 1.0),
        "validate_staging": (1.5, 3.0),
    }

    def tool_delay(self, tool_name: str, **kwargs: Any) -> tuple[float, float]:
        return self._TOOL_DELAYS.get(tool_name, (0.0, 0.0))

    # -- Tool implementations --

    def implement_feature(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Implement a feature. Requires holding repo."""
        feature = kwargs.get("feature_name") or kwargs.get("feature", "unknown")

        self._mark_done(self._implement_done, agent_id, feature)

        result = {"feature": feature, "status": "implemented", "agent": agent_id}
        self.log_event(agent_id, "implement_feature", {"feature": feature},
                       success=True, result=result)
        return ToolResult(tool_name="implement_feature", success=True,
                          data=result, message=f"Implemented: {feature}")

    def write_tests(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Write tests. Requires holding test_env."""
        component = kwargs.get("component") or kwargs.get("target", "unknown")

        self._mark_done(self._write_tests_done, agent_id, component)

        result = {"component": component, "status": "tests written", "agent": agent_id}
        self.log_event(agent_id, "write_tests", {"component": component},
                       success=True, result=result)
        return ToolResult(tool_name="write_tests", success=True,
                          data=result, message=f"Tests written for: {component}")

    def code_review(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Review code. No resource required."""
        target = kwargs.get("pr_id") or kwargs.get("target", "unknown")

        if self.should_fail("code_review", agent_id):
            result = {"target": target, "status": "changes_requested", "agent": agent_id}
            self.log_event(agent_id, "code_review", {"target": target},
                           success=False, result=result)
            return ToolResult(tool_name="code_review", success=False,
                              data=result, message=f"Code review requests changes: {target}")

        self._mark_done(self._code_review_done, agent_id, target)

        result = {"target": target, "status": "reviewed", "agent": agent_id}
        self.log_event(agent_id, "code_review", {"target": target},
                       success=True, result=result)
        return ToolResult(tool_name="code_review", success=True,
                          data=result, message=f"Code reviewed: {target}")

    def run_tests(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Run tests. Requires holding build_server."""
        suite = kwargs.get("suite", "unknown")

        if self.should_fail("run_tests", agent_id):
            result = {"suite": suite, "status": "tests_failed", "agent": agent_id}
            self.log_event(agent_id, "run_tests", {"suite": suite},
                           success=False, result=result)
            return ToolResult(tool_name="run_tests", success=False,
                              data=result, message=f"Tests FAILED: {suite}")

        self._mark_done(self._run_tests_done, agent_id, suite)

        result = {"suite": suite, "status": "tests passed", "agent": agent_id}
        self.log_event(agent_id, "run_tests", {"suite": suite},
                       success=True, result=result)
        return ToolResult(tool_name="run_tests", success=True,
                          data=result, message=f"Tests passed: {suite}")

    def merge_code(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Merge code. Requires holding repo."""
        branch = kwargs.get("branch", "unknown")

        self._mark_done(self._merge_done, agent_id, branch)

        result = {"branch": branch, "status": "merged", "agent": agent_id}
        self.log_event(agent_id, "merge_code", {"branch": branch},
                       success=True, result=result)
        return ToolResult(tool_name="merge_code", success=True,
                          data=result, message=f"Merged: {branch}")

    def deploy_service(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Deploy a service. Requires holding staging_env."""
        service = kwargs.get("service", "unknown")

        self._mark_done(self._deploy_done, agent_id, service)

        result = {"service": service, "status": "deployed", "agent": agent_id}
        self.log_event(agent_id, "deploy_service", {"service": service},
                       success=True, result=result)
        return ToolResult(tool_name="deploy_service", success=True,
                          data=result, message=f"Deployed: {service}")

    def rollback_service(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Rollback a service. Requires holding staging_env."""
        service = kwargs.get("service", "unknown")

        self._mark_done(self._rollback_done, agent_id, service)

        result = {"service": service, "status": "rolled back", "agent": agent_id}
        self.log_event(agent_id, "rollback_service", {"service": service},
                       success=True, result=result)
        return ToolResult(tool_name="rollback_service", success=True,
                          data=result, message=f"Rolled back: {service}")

    def validate_staging(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Validate staging environment. Requires holding staging_env."""
        service = kwargs.get("service") or kwargs.get("environment", "unknown")

        if self.should_fail("validate_staging", agent_id):
            result = {"service": service, "status": "validation_failed", "agent": agent_id}
            self.log_event(agent_id, "validate_staging", {"service": service},
                           success=False, result=result)
            return ToolResult(tool_name="validate_staging", success=False,
                              data=result, message=f"Staging validation FAILED: {service}")

        self._mark_done(self._validate_staging_done, agent_id, service)

        result = {"service": service, "status": "validated", "agent": agent_id}
        self.log_event(agent_id, "validate_staging", {"service": service},
                       success=True, result=result)
        return ToolResult(tool_name="validate_staging", success=True,
                          data=result, message=f"Staging validated: {service}")

    # -- SimContext interface --

    def make_tools(self) -> dict[str, Any]:
        return {
            "implement_feature": self.implement_feature,
            "write_tests": self.write_tests,
            "code_review": self.code_review,
            "run_tests": self.run_tests,
            "merge_code": self.merge_code,
            "deploy_service": self.deploy_service,
            "rollback_service": self.rollback_service,
            "validate_staging": self.validate_staging,
        }

    def is_complete(self) -> bool:
        # Required: core workflow steps that always happen.
        required = (all(self._implement_done.values()) and
                    all(self._write_tests_done.values()) and
                    all(self._code_review_done.values()) and
                    all(self._run_tests_done.values()) and
                    all(self._deploy_done.values()) and
                    all(self._validate_staging_done.values()))
        # Optional: merge_code is a domain-only tool between coordination
        # steps (acquire→release) that LLMs commonly skip; rollbacks only
        # happen on deployment failure.  Both tracked in progress but don't
        # block completion.
        return required

    @property
    def progress(self) -> dict[str, Any]:
        return {
            "implementations": dict(self._implement_done),
            "test_writes": dict(self._write_tests_done),
            "code_reviews": dict(self._code_review_done),
            "test_runs": dict(self._run_tests_done),
            "merges": dict(self._merge_done),
            "deployments": dict(self._deploy_done),
            "rollbacks": dict(self._rollback_done),
            "staging_validations": dict(self._validate_staging_done),
            "all_complete": self.is_complete(),
        }
