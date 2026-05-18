"""API system development simulation config for task 8E."""

import json
from pathlib import Path

from benchmark.tools.sim_api_system import (
    APISystemSim,
    ImplementBackendStep,
    IntegrationTestStep,
    MigrateSchemaStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "8E" / "metadata.json").read_text()
)

_RESOURCES = ["DATABASE", "TEST_ENV"]

_IMPLEMENT_BACKEND_STEPS = [
    ImplementBackendStep(agent_id="BACKEND_DEV", component="new_api_endpoints"),
]

_MIGRATE_SCHEMA_STEPS = [
    MigrateSchemaStep(agent_id="DB_ADMIN", migration_name="add_new_tables"),
]

_INTEGRATION_TEST_STEPS = [
    IntegrationTestStep(agent_id="TESTER", suite="backend_schema_integration"),
]

class BackendDatabaseSyncSim(APISystemSim):
    """8E: Backend developer, DB admin, and tester synchronizing
    database schema changes with backend implementation.

    run_integration_tests has can_fail:true (the description models a
    test-fail branch where BACKEND_DEV reports failure and finishes).
    The base-class _DECISION_TOOLS (run_integration_tests: 0.3) is
    inherited so --scenario/--difficulty can inject test failures.
    """

    def __init__(self) -> None:
        super().__init__(
            implement_backend_steps=_IMPLEMENT_BACKEND_STEPS,
            migrate_schema_steps=_MIGRATE_SCHEMA_STEPS,
            integration_test_steps=_INTEGRATION_TEST_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
