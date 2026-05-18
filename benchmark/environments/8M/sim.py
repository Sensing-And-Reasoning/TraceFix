"""API system development simulation config for task 8M."""

import json
from pathlib import Path

from benchmark.tools.sim_api_system import (
    APISystemSim,
    CodeReviewStep,
    DefineAPIStep,
    ImplementBackendStep,
    ImplementFrontendStep,
    IntegrationTestStep,
    MigrateSchemaStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "8M" / "metadata.json").read_text()
)

_RESOURCES = ["API_GATEWAY", "DATABASE", "TEST_ENV"]

_IMPLEMENT_BACKEND_STEPS = [
    ImplementBackendStep(agent_id="BACKEND_DEV", component="api_endpoints"),
]

_IMPLEMENT_FRONTEND_STEPS = [
    ImplementFrontendStep(agent_id="FRONTEND_DEV", component="user_interface"),
]

_DEFINE_API_STEPS = [
    DefineAPIStep(agent_id="BACKEND_DEV", endpoint="feature_api_spec"),
]

_MIGRATE_SCHEMA_STEPS = [
    MigrateSchemaStep(agent_id="DB_ADMIN", migration_name="feature_schema"),
]

_CODE_REVIEW_STEPS = [
    CodeReviewStep(agent_id="REVIEWER", pr_id="backend_api"),
    CodeReviewStep(agent_id="REVIEWER", pr_id="frontend_ui"),
]

_INTEGRATION_TEST_STEPS = [
    IntegrationTestStep(agent_id="TESTER", suite="full_stack_integration"),
]


class FullStackAPIDevelopmentSim(APISystemSim):
    """8M: Full-stack API development with backend dev, frontend dev,
    DB admin, tester, and reviewer across three layers.

    Both code reviews and integration tests have retry loops per the
    protocol: a failed review triggers a revise cycle, and a failed test
    triggers a fix cycle.  The base class _DECISION_TOOLS (code_review and
    run_integration_tests) is therefore intentionally inherited to allow
    --scenario/--difficulty failure injection.
    """

    def __init__(self) -> None:
        super().__init__(
            implement_backend_steps=_IMPLEMENT_BACKEND_STEPS,
            implement_frontend_steps=_IMPLEMENT_FRONTEND_STEPS,
            define_api_steps=_DEFINE_API_STEPS,
            migrate_schema_steps=_MIGRATE_SCHEMA_STEPS,
            code_review_steps=_CODE_REVIEW_STEPS,
            integration_test_steps=_INTEGRATION_TEST_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
