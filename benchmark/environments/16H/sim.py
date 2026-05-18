"""CI/CD Pipeline with Blue-Green and Canary Deployment simulation for task 16H.

Seven agents share BUILD_SERVER + ARTIFACT_STORE + TEST_ENV + STAGING_ENV
+ PROD_BLUE + PROD_GREEN, plus a CANARY_SLOTS counter (initial=3).

Deadlock traps:
  1. 6-lock contention with 7 agents
  2. Counter for canary traffic (incremental acquire + full release on failure)
  3. Blue-green swap: STAGING_ENV + prod standby simultaneously
  4. DB migration ordering: must complete before service deployment
  5. Security rejection loops force rebuild cycles
  6. Cascading rollback: backend canary fail after frontend promoted
  7. 4-way deadlock: BUILD_SERVER ↔ ARTIFACT_STORE ↔ TEST_ENV ↔ STAGING_ENV
"""

from typing import Any

from benchmark.tools._base import ToolResult
from benchmark.tools.sim_base import FailureScenario, FailureSpec
from benchmark.tools.sim_cicd import (
    BuildStep, PublishStep, PullStep, TestStep,
    SmokeTestStep, CICDSim,
)

_INFRASTRUCTURE = [
    "BUILD_SERVER", "ARTIFACT_STORE", "TEST_ENV",
    "STAGING_ENV", "PROD_BLUE", "PROD_GREEN",
]

_BUILD_STEPS = [
    BuildStep(developer_id="FRONTEND_DEV", component="frontend"),
    BuildStep(developer_id="BACKEND_DEV", component="backend"),
]

_PUBLISH_STEPS = [
    PublishStep(developer_id="FRONTEND_DEV", artifact="frontend_image"),
    PublishStep(developer_id="BACKEND_DEV", artifact="backend_image"),
]

_PULL_STEPS = [
    PullStep(agent_id="QA_ENGINEER", target="test_harness"),
    PullStep(agent_id="RELEASE_ENGINEER", target="production_deploy"),
    PullStep(agent_id="SECURITY_REVIEWER", target="security_scan"),
]

_TEST_STEPS = [
    TestStep(agent_id="QA_ENGINEER", test_type="integration", suite="api_integration"),
    TestStep(agent_id="QA_ENGINEER", test_type="e2e", suite="user_flows"),
]

_SMOKE_TEST_STEPS = [
    SmokeTestStep(agent_id="RELEASE_ENGINEER", target="staging"),
    SmokeTestStep(agent_id="RELEASE_ENGINEER", target="PROD_GREEN"),
    SmokeTestStep(agent_id="RELEASE_ENGINEER", target="canary_33"),
    SmokeTestStep(agent_id="RELEASE_ENGINEER", target="canary_66"),
]

_METADATA = {
    "agents": ["BACKEND_DEV", "BUILD_MASTER", "DB_ADMIN", "FRONTEND_DEV", "QA_ENGINEER", "RELEASE_ENGINEER", "SECURITY_REVIEWER"],
    "resources": ["ARTIFACT_STORE", "BUILD_SERVER", "CANARY_SLOTS", "PROD_BLUE", "PROD_GREEN", "STAGING_ENV", "TEST_ENV"],
    "agent_resources": {
        "BACKEND_DEV": ["ARTIFACT_STORE", "BUILD_SERVER"],
        "BUILD_MASTER": [],
        "DB_ADMIN": ["BUILD_SERVER", "STAGING_ENV"],
        "FRONTEND_DEV": ["ARTIFACT_STORE", "BUILD_SERVER"],
        "QA_ENGINEER": ["ARTIFACT_STORE", "TEST_ENV"],
        "RELEASE_ENGINEER": ["ARTIFACT_STORE", "CANARY_SLOTS", "PROD_BLUE", "PROD_GREEN", "STAGING_ENV"],
        "SECURITY_REVIEWER": ["ARTIFACT_STORE"],
    },
    "tool_resource_map": {
        "compile_code": ["BUILD_SERVER"],
        "run_unit_tests": ["BUILD_SERVER"],
        "publish_artifact": ["ARTIFACT_STORE", "BUILD_SERVER"],
        "pull_artifacts": ["ARTIFACT_STORE"],
        "run_db_migration": ["BUILD_SERVER", "STAGING_ENV"],
        "run_integration_tests": ["TEST_ENV"],
        "run_e2e_tests": ["TEST_ENV"],
        "deploy_to_env": ["STAGING_ENV", "PROD_GREEN", "PROD_BLUE"],
        "run_smoke_tests": ["STAGING_ENV", "PROD_GREEN", "CANARY_SLOTS"],
        "run_security_scan": ["ARTIFACT_STORE"],
    },
}


class CICDBlueGreenCanarySim(CICDSim):
    """16H: CI/CD with blue-green canary deployment, security review, DB migration."""

    # Override: deploy_to_env has can_fail=false (always succeeds).
    # run_db_migration and run_smoke_tests can fail per tools.json.
    _DECISION_TOOLS: dict[str, float] = {
        "compile_code": 0.2,
        "run_unit_tests": 0.3,
        "run_integration_tests": 0.3,
        "run_e2e_tests": 0.3,
        "run_db_migration": 0.2,
        "run_security_scan": 0.2,
        "run_smoke_tests": 0.3,
    }

    _TOOL_RESOURCE_MAP: dict[str, list[str]] = {
        "compile_code": ["BUILD_SERVER"],
        "run_unit_tests": ["BUILD_SERVER"],
        "publish_artifact": ["BUILD_SERVER", "ARTIFACT_STORE"],
        "pull_artifacts": ["ARTIFACT_STORE"],
        "run_db_migration": ["BUILD_SERVER", "STAGING_ENV"],
        "run_integration_tests": ["TEST_ENV"],
        "run_e2e_tests": ["TEST_ENV"],
        "run_security_scan": ["ARTIFACT_STORE"],
    }

    _SMOKE_RESOURCE_MAP: dict[str, str] = {
        "staging": "STAGING_ENV",
        "PROD_GREEN": "PROD_GREEN",
        "canary_33": "PROD_GREEN",
        "canary_66": "PROD_GREEN",
    }

    _FAILURE_SCENARIOS: dict[str, FailureScenario] = {
        "security_reject": FailureScenario(
            name="security_reject",
            failures=[FailureSpec("run_security_scan", "SECURITY_REVIEWER", call_index=0)],
            description="First security scan rejects, forcing rebuild cycle",
        ),
        "canary_fail": FailureScenario(
            name="canary_fail",
            failures=[FailureSpec("run_smoke_tests", "RELEASE_ENGINEER", call_index=2)],
            description="Canary smoke test fails at 33%, triggering rollback",
        ),
        "build_fail": FailureScenario(
            name="build_fail",
            failures=[FailureSpec("compile_code", "BACKEND_DEV", call_index=0)],
            description="Backend compilation fails, forcing rebuild",
        ),
    }

    # canary_33/canary_66 smoke tests may not run if canary fails early.
    # Security scans always complete on the success path (not optional).
    _DEFAULT_OPTIONAL: set[str] = {
        "RELEASE_ENGINEER_canary_33",
        "RELEASE_ENGINEER_canary_66",
    }

    def __init__(self, scenario: str | None = None) -> None:
        super().__init__(
            build_steps=_BUILD_STEPS,
            publish_steps=_PUBLISH_STEPS,
            pull_steps=_PULL_STEPS,
            test_steps=_TEST_STEPS,
            deploy_steps=[],  # handled by deploy_to_env
            smoke_test_steps=_SMOKE_TEST_STEPS,
            infrastructure=_INFRASTRUCTURE,
        )
        # CANARY_SLOTS as shared counter (initial capacity = 3)
        self.init_resource("CANARY_SLOTS", capacity=3)

        self.load_from_metadata(_METADATA)

        # Additional progress tracking for 16H-specific tools
        self._migration_done: dict[str, bool] = {
            "DB_ADMIN_test_migration": False,
        }
        self._security_scan_done: dict[str, bool] = {
            "SECURITY_REVIEWER_frontend": False,
            "SECURITY_REVIEWER_backend": False,
        }
        self._env_deploy_done: dict[str, bool] = {
            "RELEASE_ENGINEER_STAGING_ENV": False,
            "RELEASE_ENGINEER_PROD_GREEN": False,
        }
        self._optional_items = set(self._DEFAULT_OPTIONAL)
        if scenario:
            self.configure_scenario(scenario)

    # -- 16H-specific tool methods --

    def run_db_migration(self, agent_id: str, migration_type: str) -> ToolResult:
        """Run database migration scripts. Migration can fail (test migration may reveal issues)."""
        key = f"{agent_id}_{migration_type}"
        if self.should_fail("run_db_migration", agent_id):
            result = {"migration_type": migration_type, "status": "migration_failed",
                      "admin": agent_id}
            self.log_event(agent_id, "run_db_migration", {"migration_type": migration_type},
                           success=False, result=result)
            return ToolResult(tool_name="run_db_migration", success=False,
                              data=result, message=f"Migration failed: {migration_type}")
        if key in self._migration_done:
            self._migration_done[key] = True
        result = {"migration_type": migration_type, "status": "migration complete",
                  "admin": agent_id}
        self.log_event(agent_id, "run_db_migration", {"migration_type": migration_type},
                       success=True, result=result)
        return ToolResult(tool_name="run_db_migration", success=True,
                          data=result, message=f"Migration complete: {migration_type}")

    def deploy_to_env(self, agent_id: str, environment: str) -> ToolResult:
        """Deploy artifacts to a target environment."""
        result = {"environment": environment, "status": "deployed",
                  "engineer": agent_id}
        self.log_event(agent_id, "deploy_to_env", {"environment": environment},
                       success=True, result=result)
        key = f"{agent_id}_{environment}"
        if key in self._env_deploy_done:
            self._env_deploy_done[key] = True
        return ToolResult(tool_name="deploy_to_env", success=True,
                          data=result, message=f"Deployed to: {environment}")

    def run_security_scan(self, agent_id: str, component: str) -> ToolResult:
        """Run security vulnerability scan on build artifacts."""
        if self.should_fail("run_security_scan", agent_id):
            result = {"component": component, "status": "vulnerabilities_found",
                      "reviewer": agent_id}
            self.log_event(agent_id, "run_security_scan", {"component": component},
                           success=False, result=result)
            return ToolResult(tool_name="run_security_scan", success=False,
                              data=result, message=f"Security scan failed: {component}")

        key = f"{agent_id}_{component}"
        if key in self._security_scan_done:
            self._security_scan_done[key] = True
        result = {"component": component, "status": "scan passed",
                  "reviewer": agent_id}
        self.log_event(agent_id, "run_security_scan", {"component": component},
                       success=True, result=result)
        return ToolResult(tool_name="run_security_scan", success=True,
                          data=result, message=f"Security scan passed: {component}")

    # -- Overrides --

    def make_tools(self) -> dict[str, Any]:
        return {
            "compile_code": self.compile_code,
            "run_unit_tests": self.run_unit_tests,
            "publish_artifact": self.publish_artifact,
            "pull_artifacts": self.pull_artifacts,
            "run_db_migration": self.run_db_migration,
            "run_integration_tests": self.run_integration_tests,
            "run_e2e_tests": self.run_e2e_tests,
            "deploy_to_env": self.deploy_to_env,
            "run_smoke_tests": self.run_smoke_tests,
            "run_security_scan": self.run_security_scan,
        }

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        if tool_name == "deploy_to_env":
            env = kwargs.get("environment", "")
            return [env] if env else []
        if tool_name == "run_smoke_tests":
            target = kwargs.get("target", "")
            res = self._SMOKE_RESOURCE_MAP.get(target, target)
            return [res] if res else []
        return list(self._TOOL_RESOURCE_MAP.get(tool_name, []))

    def is_complete(self) -> bool:
        return (self._check_all_done(self._compile_done) and
                self._check_all_done(self._unit_test_done) and
                self._check_all_done(self._publish_done) and
                self._check_all_done(self._pull_done) and
                self._check_all_done(self._test_done) and
                self._check_all_done(self._env_deploy_done) and
                self._check_all_done(self._smoke_test_done) and
                self._check_all_done(self._migration_done) and
                self._check_all_done(self._security_scan_done))

    @property
    def progress(self) -> dict[str, Any]:
        return {
            "compilations": dict(self._compile_done),
            "unit_tests": dict(self._unit_test_done),
            "publishes": dict(self._publish_done),
            "pulls": dict(self._pull_done),
            "tests": dict(self._test_done),
            "migrations": dict(self._migration_done),
            "security_scans": dict(self._security_scan_done),
            "env_deployments": dict(self._env_deploy_done),
            "smoke_tests": dict(self._smoke_test_done),
            "all_complete": self.is_complete(),
        }
