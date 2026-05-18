"""Parameterized API system development simulation (scenarios 8E/8M/8H)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._base import ToolResult
from .sim_base import SimContext


@dataclass
class ImplementBackendStep:
    """A backend implementation step."""

    agent_id: str
    component: str


@dataclass
class ImplementFrontendStep:
    """A frontend implementation step."""

    agent_id: str
    component: str


@dataclass
class DefineAPIStep:
    """An API definition step."""

    agent_id: str
    endpoint: str


@dataclass
class MigrateSchemaStep:
    """A schema migration step."""

    agent_id: str
    migration_name: str


@dataclass
class CodeReviewStep:
    """A code review step."""

    agent_id: str
    pr_id: str


@dataclass
class IntegrationTestStep:
    """An integration test step."""

    agent_id: str
    suite: str


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
class RegisterServiceStep:
    """A service registration step."""

    agent_id: str
    service: str


class APISystemSim(SimContext):
    """Simulation for API system development.

    Tracks per-agent progress through backend/frontend implementation,
    API definition, schema migration, testing, and deployment phases.
    Detects violations such as missing resource holds for database,
    api_gateway, test_env, and staging_env.

    Args:
        implement_backend_steps: Backend implementation steps.
        implement_frontend_steps: Frontend implementation steps.
        define_api_steps: API definition steps (need api_gateway).
        migrate_schema_steps: Schema migration steps (need database).
        code_review_steps: Code review steps.
        integration_test_steps: Integration test steps (need test_env).
        deploy_steps: Service deployment steps (need staging_env).
        rollback_steps: Service rollback steps (need staging_env).
        register_service_steps: Service registration steps (need api_gateway).
        resources: List of shared resource names.
    """

    def __init__(
        self,
        implement_backend_steps: list[ImplementBackendStep] | None = None,
        implement_frontend_steps: list[ImplementFrontendStep] | None = None,
        define_api_steps: list[DefineAPIStep] | None = None,
        migrate_schema_steps: list[MigrateSchemaStep] | None = None,
        code_review_steps: list[CodeReviewStep] | None = None,
        integration_test_steps: list[IntegrationTestStep] | None = None,
        deploy_steps: list[DeployStep] | None = None,
        rollback_steps: list[RollbackStep] | None = None,
        register_service_steps: list[RegisterServiceStep] | None = None,
        resources: list[str] | None = None,
    ) -> None:
        super().__init__()

        self._implement_backend_steps = {f"{s.agent_id}_{s.component}": s for s in (implement_backend_steps or [])}
        self._implement_frontend_steps = {f"{s.agent_id}_{s.component}": s for s in (implement_frontend_steps or [])}
        self._define_api_steps = {f"{s.agent_id}_{s.endpoint}": s for s in (define_api_steps or [])}
        self._migrate_schema_steps = {f"{s.agent_id}_{s.migration_name}": s for s in (migrate_schema_steps or [])}
        self._code_review_steps = {f"{s.agent_id}_{s.pr_id}": s for s in (code_review_steps or [])}
        self._integration_test_steps = {f"{s.agent_id}_{s.suite}": s for s in (integration_test_steps or [])}
        self._deploy_steps = {f"{s.agent_id}_{s.service}": s for s in (deploy_steps or [])}
        self._rollback_steps = {f"{s.agent_id}_{s.service}": s for s in (rollback_steps or [])}
        self._register_service_steps = {f"{s.agent_id}_{s.service}": s for s in (register_service_steps or [])}

        self._implement_backend_done: dict[str, bool] = {k: False for k in self._implement_backend_steps}
        self._implement_frontend_done: dict[str, bool] = {k: False for k in self._implement_frontend_steps}
        self._define_api_done: dict[str, bool] = {k: False for k in self._define_api_steps}
        self._migrate_schema_done: dict[str, bool] = {k: False for k in self._migrate_schema_steps}
        self._code_review_done: dict[str, bool] = {k: False for k in self._code_review_steps}
        self._integration_test_done: dict[str, bool] = {k: False for k in self._integration_test_steps}
        self._deploy_done: dict[str, bool] = {k: False for k in self._deploy_steps}
        self._rollback_done: dict[str, bool] = {k: False for k in self._rollback_steps}
        self._register_service_done: dict[str, bool] = {k: False for k in self._register_service_steps}

        for res in (resources or []):
            self.init_resource(res)

    # -- Decision tools (probabilistic failure for either/or branches) --

    _DECISION_TOOLS: dict[str, float] = {
        "code_review": 0.3,
        "deploy_service": 0.3,
        "run_integration_tests": 0.3,
    }

    # -- Resource requirements --

    _TOOL_RESOURCES: dict[str, list[str]] = {
        "implement_backend": [],
        "implement_frontend": [],
        "define_api": ["API_GATEWAY"],
        "migrate_schema": ["DATABASE"],
        "code_review": [],
        "run_integration_tests": ["TEST_ENV"],
        "deploy_service": ["STAGING_ENV"],
        "rollback_service": ["STAGING_ENV"],
        "register_service": ["API_GATEWAY"],
    }

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        return list(self._TOOL_RESOURCES.get(tool_name, []))

    # -- Simulated delays --

    _TOOL_DELAYS: dict[str, tuple[float, float]] = {
        "implement_backend": (1.5, 4.0),
        "implement_frontend": (1.5, 4.0),
        "define_api": (0.5, 1.5),
        "migrate_schema": (1.0, 2.0),
        "code_review": (1.0, 2.0),
        "run_integration_tests": (3.0, 6.0),
        "deploy_service": (1.0, 3.0),
        "rollback_service": (0.5, 1.0),
        "register_service": (0.5, 1.0),
    }

    def tool_delay(self, tool_name: str, **kwargs: Any) -> tuple[float, float]:
        return self._TOOL_DELAYS.get(tool_name, (0.0, 0.0))

    # -- Tool implementations --

    def implement_backend(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Implement backend component. No resource required."""
        component = kwargs.get("component", "unknown")

        self._mark_done(self._implement_backend_done, agent_id, component)

        result = {"component": component, "status": "implemented", "agent": agent_id}
        self.log_event(agent_id, "implement_backend", {"component": component},
                       success=True, result=result)
        return ToolResult(tool_name="implement_backend", success=True,
                          data=result, message=f"Backend implemented: {component}")

    def implement_frontend(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Implement frontend component. No resource required."""
        component = kwargs.get("component", "unknown")

        self._mark_done(self._implement_frontend_done, agent_id, component)

        result = {"component": component, "status": "implemented", "agent": agent_id}
        self.log_event(agent_id, "implement_frontend", {"component": component},
                       success=True, result=result)
        return ToolResult(tool_name="implement_frontend", success=True,
                          data=result, message=f"Frontend implemented: {component}")

    def define_api(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Define an API. Requires holding api_gateway."""
        endpoint = kwargs.get("endpoint", "unknown")

        self._mark_done(self._define_api_done, agent_id, endpoint)

        result = {"endpoint": endpoint, "status": "defined", "agent": agent_id}
        self.log_event(agent_id, "define_api", {"endpoint": endpoint},
                       success=True, result=result)
        return ToolResult(tool_name="define_api", success=True,
                          data=result, message=f"API defined: {endpoint}")

    def migrate_schema(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Migrate database schema. Requires holding database."""
        migration_name = kwargs.get("migration_name", "unknown")

        self._mark_done(self._migrate_schema_done, agent_id, migration_name)

        result = {"migration_name": migration_name, "status": "migrated", "agent": agent_id}
        self.log_event(agent_id, "migrate_schema", {"migration_name": migration_name},
                       success=True, result=result)
        return ToolResult(tool_name="migrate_schema", success=True,
                          data=result, message=f"Schema migrated: {migration_name}")

    def code_review(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Review code. No resource required."""
        pr_id = kwargs.get("pr_id", "unknown")

        if self.should_fail("code_review", agent_id):
            result = {"pr_id": pr_id, "status": "changes_requested", "agent": agent_id}
            self.log_event(agent_id, "code_review", {"pr_id": pr_id},
                           success=False, result=result)
            return ToolResult(tool_name="code_review", success=False,
                              data=result, message=f"Code review requests changes: {pr_id}")

        self._mark_done(self._code_review_done, agent_id, pr_id)

        result = {"pr_id": pr_id, "status": "reviewed", "agent": agent_id}
        self.log_event(agent_id, "code_review", {"pr_id": pr_id},
                       success=True, result=result)
        return ToolResult(tool_name="code_review", success=True,
                          data=result, message=f"Code reviewed: {pr_id}")

    def run_integration_tests(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Run integration tests. Requires holding test_env."""
        suite = kwargs.get("suite", "unknown")

        if self.should_fail("run_integration_tests", agent_id):
            result = {"suite": suite, "status": "tests_failed", "agent": agent_id}
            self.log_event(agent_id, "run_integration_tests", {"suite": suite},
                           success=False, result=result)
            return ToolResult(tool_name="run_integration_tests", success=False,
                              data=result, message=f"Integration tests FAILED: {suite}")

        self._mark_done(self._integration_test_done, agent_id, suite)

        result = {"suite": suite, "status": "tests passed", "agent": agent_id}
        self.log_event(agent_id, "run_integration_tests", {"suite": suite},
                       success=True, result=result)
        return ToolResult(tool_name="run_integration_tests", success=True,
                          data=result, message=f"Integration tests passed: {suite}")

    def deploy_service(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Deploy a service. Requires holding staging_env."""
        service = kwargs.get("service", "unknown")

        if self.should_fail("deploy_service", agent_id):
            result = {"service": service, "status": "deploy_failed", "agent": agent_id}
            self.log_event(agent_id, "deploy_service", {"service": service},
                           success=False, result=result)
            return ToolResult(tool_name="deploy_service", success=False,
                              data=result, message=f"Deployment FAILED: {service}")

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

    def register_service(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Register a service. Requires holding api_gateway."""
        service = kwargs.get("service_name") or kwargs.get("service", "unknown")

        self._mark_done(self._register_service_done, agent_id, service)

        result = {"service": service, "status": "registered", "agent": agent_id}
        self.log_event(agent_id, "register_service", {"service": service},
                       success=True, result=result)
        return ToolResult(tool_name="register_service", success=True,
                          data=result, message=f"Registered: {service}")

    # -- SimContext interface --

    def make_tools(self) -> dict[str, Any]:
        return {
            "implement_backend": self.implement_backend,
            "implement_frontend": self.implement_frontend,
            "define_api": self.define_api,
            "migrate_schema": self.migrate_schema,
            "code_review": self.code_review,
            "run_integration_tests": self.run_integration_tests,
            "deploy_service": self.deploy_service,
            "rollback_service": self.rollback_service,
            "register_service": self.register_service,
        }

    def is_complete(self) -> bool:
        # Rollbacks are contingency steps (only triggered on deploy failure),
        # so they are NOT required for completion on the happy path.
        return (all(self._implement_backend_done.values()) and
                all(self._implement_frontend_done.values()) and
                all(self._define_api_done.values()) and
                all(self._migrate_schema_done.values()) and
                all(self._code_review_done.values()) and
                all(self._integration_test_done.values()) and
                all(self._deploy_done.values()) and
                all(self._register_service_done.values()))

    @property
    def progress(self) -> dict[str, Any]:
        return {
            "backend_implementations": dict(self._implement_backend_done),
            "frontend_implementations": dict(self._implement_frontend_done),
            "api_definitions": dict(self._define_api_done),
            "schema_migrations": dict(self._migrate_schema_done),
            "code_reviews": dict(self._code_review_done),
            "integration_tests": dict(self._integration_test_done),
            "deployments": dict(self._deploy_done),
            "rollbacks": dict(self._rollback_done),
            "service_registrations": dict(self._register_service_done),
            "all_complete": self.is_complete(),
        }
