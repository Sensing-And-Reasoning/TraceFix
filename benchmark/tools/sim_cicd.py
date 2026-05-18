"""Parameterized CI/CD pipeline simulation for task 5A."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._base import ToolResult
from .sim_base import SimContext


@dataclass
class BuildStep:
    """A compile + unit-test step for one developer."""

    developer_id: str
    component: str  # "frontend" or "backend"


@dataclass
class PublishStep:
    """An artifact publish step for one developer."""

    developer_id: str
    artifact: str  # "frontend_image" or "backend_image"


@dataclass
class PullStep:
    """An artifact pull step for one agent."""

    agent_id: str
    target: str  # "test_harness", "staging_deploy", "production_deploy"


@dataclass
class TestStep:
    """A test step (integration or E2E)."""

    agent_id: str
    test_type: str  # "integration" or "e2e"
    suite: str


@dataclass
class DeployStep:
    """A deployment step."""

    agent_id: str
    target: str  # "staging" or "production"
    component: str


@dataclass
class SmokeTestStep:
    """A smoke test step."""

    agent_id: str
    target: str  # "staging" or "production"


class CICDSim(SimContext):
    """Simulation for CI/CD pipeline with shared infrastructure.

    Tracks per-agent progress through build, test, and deploy phases.
    Detects violations such as missing infrastructure holds and
    prerequisite ordering issues.

    Args:
        build_steps: Compile + test steps (each needs build_server).
        publish_steps: Artifact publish steps (each needs build_server + artifact_store).
        pull_steps: Artifact pull steps (each needs artifact_store).
        test_steps: Integration/E2E test steps (each needs test_env).
        deploy_steps: Deployment steps (staging needs test_env, prod needs prod_env).
        smoke_test_steps: Smoke test steps.
        infrastructure: List of shared infrastructure names.
    """

    # -- Decision tools (probabilistic failure for either/or branches) --

    _DECISION_TOOLS: dict[str, float] = {
        "compile_code": 0.2,
        "run_unit_tests": 0.3,
        "run_integration_tests": 0.3,
        "run_e2e_tests": 0.3,
        "deploy_staging": 0.2,
        "deploy_production": 0.2,
        "run_smoke_tests": 0.3,
    }

    def __init__(
        self,
        build_steps: list[BuildStep],
        publish_steps: list[PublishStep],
        pull_steps: list[PullStep],
        test_steps: list[TestStep],
        deploy_steps: list[DeployStep],
        smoke_test_steps: list[SmokeTestStep],
        infrastructure: list[str],
    ) -> None:
        super().__init__()

        self._infrastructure = list(infrastructure)

        # Build lookup dicts keyed by "agent_component"
        self._build_steps = {f"{s.developer_id}_{s.component}": s for s in build_steps}
        self._publish_steps = {f"{s.developer_id}_{s.artifact}": s for s in publish_steps}
        self._pull_steps = {f"{s.agent_id}_{s.target}": s for s in pull_steps}
        self._test_steps = {f"{s.agent_id}_{s.suite}": s for s in test_steps}
        self._deploy_steps = {f"{s.agent_id}_{s.target}": s for s in deploy_steps}
        self._smoke_test_steps = {f"{s.agent_id}_{s.target}": s for s in smoke_test_steps}

        # Progress tracking
        self._compile_done: dict[str, bool] = {k: False for k in self._build_steps}
        self._unit_test_done: dict[str, bool] = {k: False for k in self._build_steps}
        self._publish_done: dict[str, bool] = {k: False for k in self._publish_steps}
        self._pull_done: dict[str, bool] = {k: False for k in self._pull_steps}
        self._test_done: dict[str, bool] = {k: False for k in self._test_steps}
        self._deploy_done: dict[str, bool] = {k: False for k in self._deploy_steps}
        self._smoke_test_done: dict[str, bool] = {k: False for k in self._smoke_test_steps}

        # Initialize infrastructure as resources
        for infra in infrastructure:
            self.init_resource(infra)

    # -- Resource requirements (for concurrent usage detection) --

    _TOOL_RESOURCES: dict[str, list[str]] = {
        "compile_code": ["BUILD_SERVER"],
        "run_unit_tests": ["BUILD_SERVER"],
        "publish_artifact": ["BUILD_SERVER", "ARTIFACT_STORE"],
        "pull_artifacts": ["ARTIFACT_STORE"],
        "run_integration_tests": ["TEST_ENV"],
        "run_e2e_tests": ["TEST_ENV"],
        "deploy_staging": ["TEST_ENV"],
        "deploy_production": ["PROD_ENV"],
    }

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        if tool_name == "run_smoke_tests":
            target = kwargs.get("target", "staging")
            return ["TEST_ENV" if target == "staging" else "PROD_ENV"]
        return list(self._TOOL_RESOURCES.get(tool_name, []))

    # -- Simulated business-logic processing times --

    _TOOL_DELAYS: dict[str, tuple[float, float]] = {
        "compile_code":            (2.0, 5.0),
        "run_unit_tests":          (1.5, 4.0),
        "publish_artifact":        (1.0, 2.0),
        "pull_artifacts":          (0.5, 1.5),
        "run_integration_tests":   (3.0, 6.0),
        "run_e2e_tests":           (3.0, 6.0),
        "deploy_staging":          (1.0, 3.0),
        "deploy_production":       (1.0, 3.0),
        "run_smoke_tests":         (1.0, 2.0),
    }

    def tool_delay(self, tool_name: str, **kwargs: Any) -> tuple[float, float]:
        return self._TOOL_DELAYS.get(tool_name, (0.0, 0.0))

    # -- Tool implementations --

    def compile_code(self, agent_id: str, component: str) -> ToolResult:
        """Compile code for a component."""
        if self.should_fail("compile_code", agent_id):
            result = {"component": component, "status": "compilation_failed", "developer": agent_id}
            self.log_event(agent_id, "compile_code", {"component": component},
                           success=False, result=result)
            return ToolResult(tool_name="compile_code", success=False,
                              data=result, message=f"Compilation failed: {component}")

        self._mark_done(self._compile_done, agent_id, component)
        result = {"component": component, "status": "compiled", "developer": agent_id}
        self.log_event(agent_id, "compile_code", {"component": component},
                       success=True, result=result)
        return ToolResult(tool_name="compile_code", success=True,
                          data=result, message=f"Compiled: {component}")

    def run_unit_tests(self, agent_id: str, component: str) -> ToolResult:
        """Run unit tests for a component."""
        if self.should_fail("run_unit_tests", agent_id):
            result = {"component": component, "status": "tests_failed", "developer": agent_id}
            self.log_event(agent_id, "run_unit_tests", {"component": component},
                           success=False, result=result)
            return ToolResult(tool_name="run_unit_tests", success=False,
                              data=result, message=f"Unit tests failed: {component}")

        self._mark_done(self._unit_test_done, agent_id, component)
        result = {"component": component, "status": "tests passed", "developer": agent_id}
        self.log_event(agent_id, "run_unit_tests", {"component": component},
                       success=True, result=result)
        return ToolResult(tool_name="run_unit_tests", success=True,
                          data=result, message=f"Unit tests passed: {component}")

    def publish_artifact(self, agent_id: str, artifact: str) -> ToolResult:
        """Publish a build artifact to the registry."""
        self._mark_done(self._publish_done, agent_id, artifact)

        result = {"artifact": artifact, "status": "published", "developer": agent_id}
        self.log_event(agent_id, "publish_artifact", {"artifact": artifact},
                       success=True, result=result)
        return ToolResult(tool_name="publish_artifact", success=True,
                          data=result, message=f"Published: {artifact}")

    def pull_artifacts(self, agent_id: str, target: str) -> ToolResult:
        """Pull artifacts from the registry."""
        self._mark_done(self._pull_done, agent_id, target)

        result = {"target": target, "status": "pulled", "agent": agent_id}
        self.log_event(agent_id, "pull_artifacts", {"target": target},
                       success=True, result=result)
        return ToolResult(tool_name="pull_artifacts", success=True,
                          data=result, message=f"Artifacts pulled for: {target}")

    def run_integration_tests(self, agent_id: str, suite: str) -> ToolResult:
        """Run integration tests for a suite."""
        if self.should_fail("run_integration_tests", agent_id):
            result = {"suite": suite, "status": "tests_failed", "engineer": agent_id}
            self.log_event(agent_id, "run_integration_tests", {"suite": suite},
                           success=False, result=result)
            return ToolResult(tool_name="run_integration_tests", success=False,
                              data=result, message=f"Integration tests failed: {suite}")

        self._mark_done(self._test_done, agent_id, suite)
        result = {"suite": suite, "status": "tests passed", "engineer": agent_id}
        self.log_event(agent_id, "run_integration_tests", {"suite": suite},
                       success=True, result=result)
        return ToolResult(tool_name="run_integration_tests", success=True,
                          data=result, message=f"Integration tests passed: {suite}")

    def run_e2e_tests(self, agent_id: str, suite: str) -> ToolResult:
        """Run end-to-end tests for a suite."""
        if self.should_fail("run_e2e_tests", agent_id):
            result = {"suite": suite, "status": "tests_failed", "engineer": agent_id}
            self.log_event(agent_id, "run_e2e_tests", {"suite": suite},
                           success=False, result=result)
            return ToolResult(tool_name="run_e2e_tests", success=False,
                              data=result, message=f"E2E tests failed: {suite}")

        self._mark_done(self._test_done, agent_id, suite)
        result = {"suite": suite, "status": "tests passed", "engineer": agent_id}
        self.log_event(agent_id, "run_e2e_tests", {"suite": suite},
                       success=True, result=result)
        return ToolResult(tool_name="run_e2e_tests", success=True,
                          data=result, message=f"E2E tests passed: {suite}")

    def deploy_staging(self, agent_id: str, component: str) -> ToolResult:
        """Deploy a component to the staging environment."""
        if self.should_fail("deploy_staging", agent_id):
            result = {"component": component, "status": "deploy_failed", "engineer": agent_id}
            self.log_event(agent_id, "deploy_staging", {"component": component},
                           success=False, result=result)
            return ToolResult(tool_name="deploy_staging", success=False,
                              data=result, message=f"Staging deploy failed: {component}")

        self._mark_done(self._deploy_done, agent_id, "staging")
        result = {"component": component, "status": "deployed to staging", "engineer": agent_id}
        self.log_event(agent_id, "deploy_staging", {"component": component},
                       success=True, result=result)
        return ToolResult(tool_name="deploy_staging", success=True,
                          data=result, message=f"Deployed to staging: {component}")

    def deploy_production(self, agent_id: str, component: str) -> ToolResult:
        """Deploy a component to the production environment."""
        if self.should_fail("deploy_production", agent_id):
            result = {"component": component, "status": "deploy_failed", "engineer": agent_id}
            self.log_event(agent_id, "deploy_production", {"component": component},
                           success=False, result=result)
            return ToolResult(tool_name="deploy_production", success=False,
                              data=result, message=f"Production deploy failed: {component}")

        self._mark_done(self._deploy_done, agent_id, "production")
        result = {"component": component, "status": "deployed to production", "engineer": agent_id}
        self.log_event(agent_id, "deploy_production", {"component": component},
                       success=True, result=result)
        return ToolResult(tool_name="deploy_production", success=True,
                          data=result, message=f"Deployed to production: {component}")

    def run_smoke_tests(self, agent_id: str, target: str) -> ToolResult:
        """Run smoke tests against a target environment."""
        if self.should_fail("run_smoke_tests", agent_id):
            result = {"target": target, "status": "smoke_tests_failed", "engineer": agent_id}
            self.log_event(agent_id, "run_smoke_tests", {"target": target},
                           success=False, result=result)
            return ToolResult(tool_name="run_smoke_tests", success=False,
                              data=result, message=f"Smoke tests failed: {target}")

        self._mark_done(self._smoke_test_done, agent_id, target)
        result = {"target": target, "status": "smoke tests passed", "engineer": agent_id}
        self.log_event(agent_id, "run_smoke_tests", {"target": target},
                       success=True, result=result)
        return ToolResult(tool_name="run_smoke_tests", success=True,
                          data=result, message=f"Smoke tests passed: {target}")

    # -- SimContext interface --

    def make_tools(self) -> dict[str, Any]:
        """Return tool dispatch dict for sim-mode registry."""
        return {
            "compile_code": self.compile_code,
            "run_unit_tests": self.run_unit_tests,
            "publish_artifact": self.publish_artifact,
            "pull_artifacts": self.pull_artifacts,
            "run_integration_tests": self.run_integration_tests,
            "run_e2e_tests": self.run_e2e_tests,
            "deploy_staging": self.deploy_staging,
            "deploy_production": self.deploy_production,
            "run_smoke_tests": self.run_smoke_tests,
        }

    def is_complete(self) -> bool:
        """All build, test, and deploy steps must be completed (optional items skipped)."""
        return (self._check_all_done(self._compile_done) and
                self._check_all_done(self._unit_test_done) and
                self._check_all_done(self._publish_done) and
                self._check_all_done(self._pull_done) and
                self._check_all_done(self._test_done) and
                self._check_all_done(self._deploy_done) and
                self._check_all_done(self._smoke_test_done))

    @property
    def progress(self) -> dict[str, Any]:
        """Current progress toward the goal."""
        return {
            "compilations": dict(self._compile_done),
            "unit_tests": dict(self._unit_test_done),
            "publishes": dict(self._publish_done),
            "pulls": dict(self._pull_done),
            "tests": dict(self._test_done),
            "deployments": dict(self._deploy_done),
            "smoke_tests": dict(self._smoke_test_done),
            "all_complete": self.is_complete(),
        }
