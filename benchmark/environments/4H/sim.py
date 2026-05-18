"""Code Collaboration simulation config for task 4H."""

import json
from pathlib import Path
from typing import Any

from benchmark.tools.sim_code_collab import (
    CodeCollabSim,
    CodeReviewStep,
    DeployStep,
    DesignProposalStep,
    ImplementStep,
    MigrateSchemaStep,
    RegisterServiceStep,
    RunTestsStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "4H" / "metadata.json").read_text()
)

_RESOURCES = ["STAGING_ENV", "TEST_ENV"]

_DESIGN_PROPOSAL_STEPS = [
    DesignProposalStep(agent_id="ARCHITECT", proposal="migration_plan"),
]

_IMPLEMENT_STEPS = [
    ImplementStep(agent_id="DEVELOPER_A", feature="microservice_a"),
    ImplementStep(agent_id="DEVELOPER_B", feature="microservice_b"),
    ImplementStep(agent_id="DEVELOPER_C", feature="microservice_c"),
]

_CODE_REVIEW_STEPS = [
    CodeReviewStep(agent_id="REVIEWER", target="microservice_a"),
    CodeReviewStep(agent_id="REVIEWER", target="microservice_b"),
    CodeReviewStep(agent_id="REVIEWER", target="microservice_c"),
]

_RUN_TESTS_STEPS = [
    RunTestsStep(agent_id="TESTER", suite="microservice_a"),
    RunTestsStep(agent_id="TESTER", suite="microservice_b"),
    RunTestsStep(agent_id="TESTER", suite="microservice_c"),
]

_MIGRATE_SCHEMA_STEPS = [
    MigrateSchemaStep(agent_id="DEVOPS", migration="microservice_a_schema"),
    MigrateSchemaStep(agent_id="DEVOPS", migration="microservice_b_schema"),
    MigrateSchemaStep(agent_id="DEVOPS", migration="microservice_c_schema"),
]

_REGISTER_SERVICE_STEPS = [
    RegisterServiceStep(agent_id="DEVOPS", service="microservice_a"),
    RegisterServiceStep(agent_id="DEVOPS", service="microservice_b"),
    RegisterServiceStep(agent_id="DEVOPS", service="microservice_c"),
]

_DEPLOY_STEPS = [
    DeployStep(agent_id="DEVOPS", service="microservice_a"),
    DeployStep(agent_id="DEVOPS", service="microservice_b"),
    DeployStep(agent_id="DEVOPS", service="microservice_c"),
]


class MicroserviceMigrationSim(CodeCollabSim):
    """4H: Microservice migration with continuous availability --
    architect, three developers, tester, reviewer, and DevOps.

    4H has no shared REPO resource.  Developers build microservices locally
    (implement_feature needs no resource), and schema migrations run as part
    of the staging deployment pipeline (migrate_schema requires STAGING_ENV).
    Overriding resource_requirements() corrects the inherited class-level
    _TOOL_RESOURCES which maps these tools to REPO.

    Retry loop is present (failed deployment -> rollback -> fix -> re-enter
    review + test + deploy), so _DECISION_TOOLS is inherited from the base
    class (code_review: 0.3, deploy_service: 0.2, run_tests: 0.3).
    """

    # Override resource requirements for tools where 4H has no REPO resource.
    _4H_TOOL_RESOURCES: dict[str, list[str]] = {
        "implement_feature": [],       # no shared repo; developers build locally
        "migrate_schema": ["STAGING_ENV"],  # migrations run in staging pipeline
    }

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        if tool_name in self._4H_TOOL_RESOURCES:
            return list(self._4H_TOOL_RESOURCES[tool_name])
        return super().resource_requirements(tool_name, **kwargs)

    def __init__(self) -> None:
        super().__init__(
            design_proposal_steps=_DESIGN_PROPOSAL_STEPS,
            implement_steps=_IMPLEMENT_STEPS,
            code_review_steps=_CODE_REVIEW_STEPS,
            run_tests_steps=_RUN_TESTS_STEPS,
            migrate_schema_steps=_MIGRATE_SCHEMA_STEPS,
            register_service_steps=_REGISTER_SERVICE_STEPS,
            deploy_steps=_DEPLOY_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
