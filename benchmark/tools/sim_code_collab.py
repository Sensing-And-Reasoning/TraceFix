"""Parameterized code collaboration simulation (scenarios 4E/4M/4H)."""

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
class DefineAPIStep:
    """An API definition step."""

    agent_id: str
    api_name: str


@dataclass
class DesignProposalStep:
    """A design proposal step."""

    agent_id: str
    proposal: str


@dataclass
class RefactorStep:
    """A code refactoring step."""

    agent_id: str
    target: str


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
class MigrateSchemaStep:
    """A schema migration step."""

    agent_id: str
    migration: str


@dataclass
class RegisterServiceStep:
    """A service registration step."""

    agent_id: str
    service: str


@dataclass
class ValidateStagingStep:
    """A staging validation step."""

    agent_id: str
    service: str


class CodeCollabSim(SimContext):
    """Simulation for multi-agent code collaboration.

    Tracks per-agent progress through implementation, review, testing, merge,
    and deployment phases.  Detects violations such as missing resource holds
    for repo, test_env, and staging_env.

    Args:
        implement_steps: Feature implementation steps (need repo by default).
        define_api_steps: API definition steps (need repo).
        design_proposal_steps: Design proposal steps.
        refactor_steps: Code refactoring steps (need repo).
        write_tests_steps: Test writing steps (need repo).
        code_review_steps: Code review steps.
        run_tests_steps: Test execution steps (need test_env).
        merge_steps: Code merge steps (need repo).
        deploy_steps: Service deployment steps (need staging_env).
        rollback_steps: Service rollback steps (need staging_env).
        migrate_schema_steps: Schema migration steps (need repo).
        register_service_steps: Service registration steps.
        validate_staging_steps: Staging validation steps (need staging_env).
        resources: List of shared resource names.
    """

    def __init__(
        self,
        implement_steps: list[ImplementStep] | None = None,
        define_api_steps: list[DefineAPIStep] | None = None,
        design_proposal_steps: list[DesignProposalStep] | None = None,
        refactor_steps: list[RefactorStep] | None = None,
        write_tests_steps: list[WriteTestsStep] | None = None,
        code_review_steps: list[CodeReviewStep] | None = None,
        run_tests_steps: list[RunTestsStep] | None = None,
        merge_steps: list[MergeStep] | None = None,
        deploy_steps: list[DeployStep] | None = None,
        rollback_steps: list[RollbackStep] | None = None,
        migrate_schema_steps: list[MigrateSchemaStep] | None = None,
        register_service_steps: list[RegisterServiceStep] | None = None,
        validate_staging_steps: list[ValidateStagingStep] | None = None,
        resources: list[str] | None = None,
    ) -> None:
        super().__init__()

        self._implement_steps = {f"{s.agent_id}_{s.feature}": s for s in (implement_steps or [])}
        self._define_api_steps = {f"{s.agent_id}_{s.api_name}": s for s in (define_api_steps or [])}
        self._design_proposal_steps = {f"{s.agent_id}_{s.proposal}": s for s in (design_proposal_steps or [])}
        self._refactor_steps = {f"{s.agent_id}_{s.target}": s for s in (refactor_steps or [])}
        self._write_tests_steps = {f"{s.agent_id}_{s.component}": s for s in (write_tests_steps or [])}
        self._code_review_steps = {f"{s.agent_id}_{s.target}": s for s in (code_review_steps or [])}
        self._run_tests_steps = {f"{s.agent_id}_{s.suite}": s for s in (run_tests_steps or [])}
        self._merge_steps = {f"{s.agent_id}_{s.branch}": s for s in (merge_steps or [])}
        self._deploy_steps = {f"{s.agent_id}_{s.service}": s for s in (deploy_steps or [])}
        self._rollback_steps = {f"{s.agent_id}_{s.service}": s for s in (rollback_steps or [])}
        self._migrate_schema_steps = {f"{s.agent_id}_{s.migration}": s for s in (migrate_schema_steps or [])}
        self._register_service_steps = {f"{s.agent_id}_{s.service}": s for s in (register_service_steps or [])}
        self._validate_staging_steps = {f"{s.agent_id}_{s.service}": s for s in (validate_staging_steps or [])}

        self._implement_done: dict[str, bool] = {k: False for k in self._implement_steps}
        self._define_api_done: dict[str, bool] = {k: False for k in self._define_api_steps}
        self._design_proposal_done: dict[str, bool] = {k: False for k in self._design_proposal_steps}
        self._refactor_done: dict[str, bool] = {k: False for k in self._refactor_steps}
        self._write_tests_done: dict[str, bool] = {k: False for k in self._write_tests_steps}
        self._code_review_done: dict[str, bool] = {k: False for k in self._code_review_steps}
        self._run_tests_done: dict[str, bool] = {k: False for k in self._run_tests_steps}
        self._merge_done: dict[str, bool] = {k: False for k in self._merge_steps}
        self._deploy_done: dict[str, bool] = {k: False for k in self._deploy_steps}
        self._rollback_done: dict[str, bool] = {k: False for k in self._rollback_steps}
        self._migrate_schema_done: dict[str, bool] = {k: False for k in self._migrate_schema_steps}
        self._register_service_done: dict[str, bool] = {k: False for k in self._register_service_steps}
        self._validate_staging_done: dict[str, bool] = {k: False for k in self._validate_staging_steps}

        for res in (resources or []):
            self.init_resource(res)

    # -- Decision tools (probabilistic failure for either/or branches) --

    _DECISION_TOOLS: dict[str, float] = {
        "code_review": 0.3,
        "deploy_service": 0.2,
        "run_tests": 0.3,
        "validate_staging": 0.2,
    }

    # -- Resource requirements --

    _TOOL_RESOURCES: dict[str, list[str]] = {
        "implement_feature": ["REPO"],
        "define_api": ["REPO"],
        "design_proposal": [],
        "refactor_code": ["REPO"],
        "write_tests": ["REPO"],
        "code_review": [],
        "run_tests": ["TEST_ENV"],
        "merge_code": ["REPO"],
        "deploy_service": ["STAGING_ENV"],
        "rollback_service": ["STAGING_ENV"],
        "migrate_schema": ["REPO"],
        "register_service": [],
        "validate_staging": ["STAGING_ENV"],
    }

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        return list(self._TOOL_RESOURCES.get(tool_name, []))

    # -- Simulated delays --

    _TOOL_DELAYS: dict[str, tuple[float, float]] = {
        "implement_feature": (1.5, 4.0),
        "define_api": (0.5, 1.5),
        "design_proposal": (0.5, 1.5),
        "refactor_code": (1.0, 3.0),
        "write_tests": (1.0, 2.5),
        "code_review": (1.0, 2.0),
        "run_tests": (2.0, 5.0),
        "merge_code": (0.5, 1.0),
        "deploy_service": (1.0, 3.0),
        "rollback_service": (0.5, 1.0),
        "migrate_schema": (1.0, 2.0),
        "register_service": (0.5, 1.0),
        "validate_staging": (1.5, 3.0),
    }

    def tool_delay(self, tool_name: str, **kwargs: Any) -> tuple[float, float]:
        return self._TOOL_DELAYS.get(tool_name, (0.0, 0.0))

    # -- Tool implementations --

    def implement_feature(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Implement a feature. Requires holding repo by default; subclasses may override."""
        feature = kwargs.get("feature_name") or kwargs.get("feature", "unknown")

        self._mark_done(self._implement_done, agent_id, feature)

        result = {"feature": feature, "status": "implemented", "agent": agent_id}
        self.log_event(agent_id, "implement_feature", {"feature": feature},
                       success=True, result=result)
        return ToolResult(tool_name="implement_feature", success=True,
                          data=result, message=f"Implemented: {feature}")

    def define_api(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Define an API specification. Requires holding repo."""
        api_name = kwargs.get("api_name") or kwargs.get("endpoint", "unknown")

        self._mark_done(self._define_api_done, agent_id, api_name)

        result = {"api_name": api_name, "status": "defined", "agent": agent_id}
        self.log_event(agent_id, "define_api", {"api_name": api_name},
                       success=True, result=result)
        return ToolResult(tool_name="define_api", success=True,
                          data=result, message=f"Defined API: {api_name}")

    def design_proposal(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Create a design proposal. No resource required."""
        proposal = kwargs.get("title") or kwargs.get("proposal", "unknown")

        self._mark_done(self._design_proposal_done, agent_id, proposal)

        result = {"proposal": proposal, "status": "proposed", "agent": agent_id}
        self.log_event(agent_id, "design_proposal", {"proposal": proposal},
                       success=True, result=result)
        return ToolResult(tool_name="design_proposal", success=True,
                          data=result, message=f"Design proposal: {proposal}")

    def refactor_code(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Refactor code. Requires holding repo."""
        target = kwargs.get("target", "unknown")

        self._mark_done(self._refactor_done, agent_id, target)

        result = {"target": target, "status": "refactored", "agent": agent_id}
        self.log_event(agent_id, "refactor_code", {"target": target},
                       success=True, result=result)
        return ToolResult(tool_name="refactor_code", success=True,
                          data=result, message=f"Refactored: {target}")

    def write_tests(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Write tests. Requires holding repo."""
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
        """Run tests. Requires holding test_env."""
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

        if self.should_fail("deploy_service", agent_id):
            result = {"service": service, "status": "deployment_failed", "agent": agent_id}
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

    def migrate_schema(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Migrate database schema. Requires holding repo by default; subclasses may override."""
        migration = kwargs.get("migration_name") or kwargs.get("migration", "unknown")

        self._mark_done(self._migrate_schema_done, agent_id, migration)

        result = {"migration": migration, "status": "migrated", "agent": agent_id}
        self.log_event(agent_id, "migrate_schema", {"migration": migration},
                       success=True, result=result)
        return ToolResult(tool_name="migrate_schema", success=True,
                          data=result, message=f"Schema migrated: {migration}")

    def register_service(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Register a service. No resource required."""
        service = kwargs.get("service_name") or kwargs.get("service", "unknown")

        self._mark_done(self._register_service_done, agent_id, service)

        result = {"service": service, "status": "registered", "agent": agent_id}
        self.log_event(agent_id, "register_service", {"service": service},
                       success=True, result=result)
        return ToolResult(tool_name="register_service", success=True,
                          data=result, message=f"Registered: {service}")

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
            "define_api": self.define_api,
            "design_proposal": self.design_proposal,
            "refactor_code": self.refactor_code,
            "write_tests": self.write_tests,
            "code_review": self.code_review,
            "run_tests": self.run_tests,
            "merge_code": self.merge_code,
            "deploy_service": self.deploy_service,
            "rollback_service": self.rollback_service,
            "migrate_schema": self.migrate_schema,
            "register_service": self.register_service,
            "validate_staging": self.validate_staging,
        }

    def is_complete(self) -> bool:
        return (self._check_all_done(self._implement_done) and
                self._check_all_done(self._define_api_done) and
                self._check_all_done(self._design_proposal_done) and
                self._check_all_done(self._refactor_done) and
                self._check_all_done(self._write_tests_done) and
                self._check_all_done(self._code_review_done) and
                self._check_all_done(self._run_tests_done) and
                self._check_all_done(self._merge_done) and
                self._check_all_done(self._deploy_done) and
                self._check_all_done(self._rollback_done) and
                self._check_all_done(self._migrate_schema_done) and
                self._check_all_done(self._register_service_done) and
                self._check_all_done(self._validate_staging_done))

    @property
    def progress(self) -> dict[str, Any]:
        return {
            "implementations": dict(self._implement_done),
            "api_definitions": dict(self._define_api_done),
            "design_proposals": dict(self._design_proposal_done),
            "refactors": dict(self._refactor_done),
            "test_writes": dict(self._write_tests_done),
            "code_reviews": dict(self._code_review_done),
            "test_runs": dict(self._run_tests_done),
            "merges": dict(self._merge_done),
            "deployments": dict(self._deploy_done),
            "rollbacks": dict(self._rollback_done),
            "schema_migrations": dict(self._migrate_schema_done),
            "service_registrations": dict(self._register_service_done),
            "staging_validations": dict(self._validate_staging_done),
            "all_complete": self.is_complete(),
        }
