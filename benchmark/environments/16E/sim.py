"""Simple CI/CD Pipeline simulation config for task 16E.

Three agents share BUILD_SERVER + DEPLOY_ENV in a linear pipeline.
No failure paths — straightforward build → test → deploy sequence.
Hazard: BUILD_SERVER contention between DEVELOPER and TESTER.
"""

from typing import Any

from benchmark.tools._base import ToolResult
from benchmark.tools.sim_cicd import (
    BuildStep, TestStep, DeployStep, SmokeTestStep, CICDSim,
)

_INFRASTRUCTURE = ["BUILD_SERVER", "DEPLOY_ENV"]

_BUILD_STEPS = [
    BuildStep(developer_id="DEVELOPER", component="application"),
]

_TEST_STEPS = [
    TestStep(agent_id="TESTER", test_type="integration", suite="integration"),
]

_DEPLOY_STEPS = [
    DeployStep(agent_id="DEPLOYER", target="production", component="application"),
]

_SMOKE_TEST_STEPS = [
    SmokeTestStep(agent_id="DEPLOYER", target="production"),
]

_METADATA = {
    "agents": ["DEPLOYER", "DEVELOPER", "TESTER"],
    "resources": ["BUILD_SERVER", "DEPLOY_ENV"],
    "agent_resources": {
        "DEVELOPER": ["BUILD_SERVER"],
        "TESTER": ["BUILD_SERVER"],
        "DEPLOYER": ["DEPLOY_ENV"],
    },
    "tool_resource_map": {
        "compile_and_test": ["BUILD_SERVER"],
        "run_integration_tests": ["BUILD_SERVER"],
        "deploy_application": ["DEPLOY_ENV"],
    },
}


class SimpleCICDSim(CICDSim):
    """16E: Simple linear CI/CD pipeline with BUILD_SERVER contention.

    Tests are terminal (pass → notify, no retry), so all tools are
    non-decision tools. Overriding _DECISION_TOOLS to empty prevents
    --scenario/--difficulty from injecting failures that would leave
    progress trackers permanently incomplete.
    """

    # No retry loop in this linear pipeline — all outcomes are terminal.
    # Disable failure injection for difficulty/scenario modes.
    _DECISION_TOOLS: dict = {}

    _FAILURE_SCENARIOS: dict = {}

    _DEFAULT_OPTIONAL: set[str] = set()

    def __init__(self, scenario: str | None = None) -> None:
        super().__init__(
            build_steps=_BUILD_STEPS,
            publish_steps=[],
            pull_steps=[],
            test_steps=_TEST_STEPS,
            deploy_steps=_DEPLOY_STEPS,
            smoke_test_steps=_SMOKE_TEST_STEPS,
            infrastructure=_INFRASTRUCTURE,
        )
        self.load_from_metadata(_METADATA)
        self._optional_items = set(self._DEFAULT_OPTIONAL)
        if scenario:
            self.configure_scenario(scenario)

    # -- Combined tool methods (16E uses simplified tools) --

    def compile_and_test(self, agent_id: str, component: str) -> ToolResult:
        """Compile and run unit tests (combined tool for 16E)."""
        key = f"{agent_id}_{component}"
        if key in self._compile_done:
            self._compile_done[key] = True
        if key in self._unit_test_done:
            self._unit_test_done[key] = True
        result = {"component": component, "status": "compiled and tested",
                  "developer": agent_id}
        self.log_event(agent_id, "compile_and_test", {"component": component},
                       success=True, result=result)
        return ToolResult(tool_name="compile_and_test", success=True,
                          data=result, message=f"Compiled and tested: {component}")

    def deploy_application(self, agent_id: str, target: str) -> ToolResult:
        """Deploy application and run smoke tests (combined tool for 16E)."""
        key = f"{agent_id}_{target}"
        if key in self._deploy_done:
            self._deploy_done[key] = True
        if key in self._smoke_test_done:
            self._smoke_test_done[key] = True
        result = {"target": target, "status": "deployed and smoke-tested",
                  "engineer": agent_id}
        self.log_event(agent_id, "deploy_application", {"target": target},
                       success=True, result=result)
        return ToolResult(tool_name="deploy_application", success=True,
                          data=result, message=f"Deployed and smoke-tested: {target}")

    # -- Overrides --

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        """Override: in 16E, run_integration_tests uses BUILD_SERVER (not TEST_ENV)."""
        if tool_name == "run_integration_tests":
            return ["BUILD_SERVER"]
        if tool_name == "deploy_application":
            return ["DEPLOY_ENV"]
        if tool_name == "compile_and_test":
            return ["BUILD_SERVER"]
        return []

    def make_tools(self) -> dict[str, Any]:
        return {
            "compile_and_test": self.compile_and_test,
            "run_integration_tests": self.run_integration_tests,
            "deploy_application": self.deploy_application,
        }
