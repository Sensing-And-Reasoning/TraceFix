"""CI/CD Pipeline simulation config for task 16M."""

from benchmark.tools.sim_base import FailureScenario, FailureSpec
from benchmark.tools.sim_cicd import (
    BuildStep, PublishStep, PullStep, TestStep,
    DeployStep, SmokeTestStep, CICDSim,
)

_INFRASTRUCTURE = ["BUILD_SERVER", "ARTIFACT_STORE", "TEST_ENV", "PROD_ENV"]

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
    PullStep(agent_id="RELEASE_ENGINEER", target="staging_deploy"),
]

_TEST_STEPS = [
    TestStep(agent_id="QA_ENGINEER", test_type="integration", suite="api_integration"),
    TestStep(agent_id="QA_ENGINEER", test_type="e2e", suite="user_flows"),
]

_DEPLOY_STEPS = [
    DeployStep(agent_id="RELEASE_ENGINEER", target="staging", component="full_stack"),
    DeployStep(agent_id="RELEASE_ENGINEER", target="production", component="full_stack"),
]

_SMOKE_TEST_STEPS = [
    SmokeTestStep(agent_id="RELEASE_ENGINEER", target="staging"),
    SmokeTestStep(agent_id="RELEASE_ENGINEER", target="production"),
]

_METADATA = {
    "agents": ["BACKEND_DEV", "BUILD_MASTER", "FRONTEND_DEV", "QA_ENGINEER", "RELEASE_ENGINEER"],
    "resources": ["ARTIFACT_STORE", "BUILD_SERVER", "PROD_ENV", "TEST_ENV"],
    "agent_resources": {
        "BACKEND_DEV": ["ARTIFACT_STORE", "BUILD_SERVER"],
        "BUILD_MASTER": [],
        "FRONTEND_DEV": ["ARTIFACT_STORE", "BUILD_SERVER"],
        "QA_ENGINEER": ["ARTIFACT_STORE", "TEST_ENV"],
        "RELEASE_ENGINEER": ["ARTIFACT_STORE", "PROD_ENV", "TEST_ENV"],
    },
    "tool_resource_map": {
        "compile_code": ["BUILD_SERVER"],
        "run_unit_tests": ["BUILD_SERVER"],
        "publish_artifact": ["ARTIFACT_STORE", "BUILD_SERVER"],
        "pull_artifacts": ["ARTIFACT_STORE"],
        "run_integration_tests": ["TEST_ENV"],
        "run_e2e_tests": ["TEST_ENV"],
        "deploy_staging": ["TEST_ENV"],
        "run_smoke_tests": ["TEST_ENV", "PROD_ENV"],
        "deploy_production": ["PROD_ENV"],
    },
}


class CICDPipelineSim(CICDSim):
    """16M: Full CI/CD pipeline with build, test, and deploy stages."""

    # Override: deploy_production has can_fail=false (terminal success only).
    # deploy_staging and run_smoke_tests can fail per tools.json.
    _DECISION_TOOLS: dict[str, float] = {
        "compile_code": 0.2,
        "run_unit_tests": 0.3,
        "run_integration_tests": 0.3,
        "run_e2e_tests": 0.3,
        "deploy_staging": 0.2,
        "run_smoke_tests": 0.3,
    }

    _FAILURE_SCENARIOS: dict[str, FailureScenario] = {
        "build_fail": FailureScenario(
            name="build_fail",
            failures=[FailureSpec("compile_code", "BACKEND_DEV", call_index=0)],
            description="Backend compilation fails, forcing rebuild",
        ),
        "qa_fail": FailureScenario(
            name="qa_fail",
            failures=[FailureSpec("run_integration_tests", "QA_ENGINEER", call_index=0)],
            description="Integration tests fail, forcing fix cycle",
        ),
        "staging_fail": FailureScenario(
            name="staging_fail",
            failures=[FailureSpec("run_smoke_tests", "RELEASE_ENGINEER", call_index=0)],
            description="Staging smoke test fails, triggering abort",
        ),
    }

    _DEFAULT_OPTIONAL: set[str] = set()

    def __init__(self, scenario: str | None = None) -> None:
        super().__init__(
            build_steps=_BUILD_STEPS,
            publish_steps=_PUBLISH_STEPS,
            pull_steps=_PULL_STEPS,
            test_steps=_TEST_STEPS,
            deploy_steps=_DEPLOY_STEPS,
            smoke_test_steps=_SMOKE_TEST_STEPS,
            infrastructure=_INFRASTRUCTURE,
        )
        self.load_from_metadata(_METADATA)
        self._optional_items = set(self._DEFAULT_OPTIONAL)
        if scenario:
            self.configure_scenario(scenario)
