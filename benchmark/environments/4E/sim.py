"""Code Collaboration simulation config for task 4E."""

import json
from pathlib import Path

from benchmark.tools.sim_code_collab import (
    CodeCollabSim,
    DefineAPIStep,
    ImplementStep,
    RunTestsStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "4E" / "metadata.json").read_text()
)

_RESOURCES = ["REPO", "TEST_ENV"]

_DEFINE_API_STEPS = [
    DefineAPIStep(agent_id="BACKEND_DEV", api_name="feature_api_spec"),
]

_IMPLEMENT_STEPS = [
    ImplementStep(agent_id="FRONTEND_DEV", feature="frontend_component"),
    ImplementStep(agent_id="BACKEND_DEV", feature="backend_endpoint"),
]

_RUN_TESTS_STEPS = [
    RunTestsStep(agent_id="TESTER", suite="integration_tests"),
]


class FrontendBackendAPISim(CodeCollabSim):
    """4E: Frontend-backend API coordination with integration testing.

    Tests are terminal (TESTER runs once, no retry regardless of result), so
    run_tests is not a decision tool.  Overriding to empty prevents
    --scenario/--difficulty from injecting failures that would leave
    _run_tests_done permanently False.
    """

    # No retry loop: test outcome is terminal.
    _DECISION_TOOLS: dict = {}

    def __init__(self) -> None:
        super().__init__(
            define_api_steps=_DEFINE_API_STEPS,
            implement_steps=_IMPLEMENT_STEPS,
            run_tests_steps=_RUN_TESTS_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
