"""API system development simulation config for task 8H."""

import json
from pathlib import Path

from benchmark.tools.sim_api_system import (
    APISystemSim,
    CodeReviewStep,
    DefineAPIStep,
    DeployStep,
    ImplementBackendStep,
    ImplementFrontendStep,
    IntegrationTestStep,
    MigrateSchemaStep,
    RegisterServiceStep,
    RollbackStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "8H" / "metadata.json").read_text()
)

_RESOURCES = ["API_GATEWAY", "DATABASE", "STAGING_ENV", "TEST_ENV"]

_IMPLEMENT_BACKEND_STEPS = [
    ImplementBackendStep(agent_id="BACKEND_A", component="service_a_user_mgmt"),
    ImplementBackendStep(agent_id="BACKEND_B", component="service_b_order_proc"),
]

_IMPLEMENT_FRONTEND_STEPS = [
    ImplementFrontendStep(agent_id="FRONTEND_DEV", component="platform_ui"),
]

_DEFINE_API_STEPS = [
    DefineAPIStep(agent_id="BACKEND_A", endpoint="service_a_api"),
    DefineAPIStep(agent_id="BACKEND_B", endpoint="service_b_api"),
]

_MIGRATE_SCHEMA_STEPS = [
    MigrateSchemaStep(agent_id="DB_ADMIN", migration_name="shared_db_schema"),
]

_CODE_REVIEW_STEPS = [
    CodeReviewStep(agent_id="REVIEWER", pr_id="service_a"),
    CodeReviewStep(agent_id="REVIEWER", pr_id="service_b"),
    CodeReviewStep(agent_id="REVIEWER", pr_id="frontend_dev"),
]

_INTEGRATION_TEST_STEPS = [
    IntegrationTestStep(agent_id="TESTER", suite="service_a_integration"),
    IntegrationTestStep(agent_id="TESTER", suite="service_b_integration"),
    IntegrationTestStep(agent_id="TESTER", suite="full_platform_integration"),
]

_DEPLOY_STEPS = [
    DeployStep(agent_id="DEV_OPS", service="service_a"),
    DeployStep(agent_id="DEV_OPS", service="service_b"),
    DeployStep(agent_id="DEV_OPS", service="frontend_dev"),
]

_ROLLBACK_STEPS = [
    RollbackStep(agent_id="DEV_OPS", service="service_a"),
    RollbackStep(agent_id="DEV_OPS", service="service_b"),
]

_REGISTER_SERVICE_STEPS = [
    RegisterServiceStep(agent_id="DEV_OPS", service="service_a"),
    RegisterServiceStep(agent_id="DEV_OPS", service="service_b"),
]


class MultiServiceAPIPlatformSim(APISystemSim):
    """8H: Multi-service API platform with two backend devs, frontend dev,
    DB admin, tester, reviewer, and DevOps engineer."""

    def __init__(self) -> None:
        super().__init__(
            implement_backend_steps=_IMPLEMENT_BACKEND_STEPS,
            implement_frontend_steps=_IMPLEMENT_FRONTEND_STEPS,
            define_api_steps=_DEFINE_API_STEPS,
            migrate_schema_steps=_MIGRATE_SCHEMA_STEPS,
            code_review_steps=_CODE_REVIEW_STEPS,
            integration_test_steps=_INTEGRATION_TEST_STEPS,
            deploy_steps=_DEPLOY_STEPS,
            rollback_steps=_ROLLBACK_STEPS,
            register_service_steps=_REGISTER_SERVICE_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
