"""Shared Codebase Development simulation config for task 1E."""

import json
from pathlib import Path

from benchmark.tools.sim_coding import (
    CodingSim,
    CommitStep,
    DesignStep,
    ImplementStep,
    TestStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "1E" / "metadata.json").read_text()
)

_RESOURCES = ["AUTH_MODULE", "DATABASE_MODULE", "API_MODULE"]

_DESIGN_STEPS = [
    DesignStep(agent_id="DEVELOPER_A", feature="user_authentication"),
    DesignStep(agent_id="DEVELOPER_B", feature="rest_api_endpoints"),
    DesignStep(agent_id="DEVELOPER_C", feature="api_auth_middleware"),
]

_IMPLEMENT_STEPS = [
    ImplementStep(agent_id="DEVELOPER_A", feature="user_authentication"),
    ImplementStep(agent_id="DEVELOPER_B", feature="rest_api_endpoints"),
    ImplementStep(agent_id="DEVELOPER_C", feature="api_auth_middleware"),
]

_COMMIT_STEPS = [
    CommitStep(agent_id="DEVELOPER_A", modules=["AUTH_MODULE", "DATABASE_MODULE"]),
    CommitStep(agent_id="DEVELOPER_B", modules=["API_MODULE", "DATABASE_MODULE"]),
    CommitStep(agent_id="DEVELOPER_C", modules=["API_MODULE", "AUTH_MODULE"]),
]

_TEST_STEPS = [
    TestStep(agent_id="DEVELOPER_A", feature="user_authentication"),
    TestStep(agent_id="DEVELOPER_B", feature="rest_api_endpoints"),
    TestStep(agent_id="DEVELOPER_C", feature="api_auth_middleware"),
]


class SharedCodebaseSim(CodingSim):
    """1E: Three developers on independent features in a shared codebase.

    Tests are terminal (pass or fail, no retry), so run_local_tests is not
    a decision tool — failure injection via --scenario/--difficulty is disabled.
    """

    # No retry loop in this task: test outcome is terminal regardless.
    # Overriding to empty prevents --scenario/--difficulty from injecting
    # failures that would leave _test_done permanently False.
    _DECISION_TOOLS: dict = {}

    def __init__(self) -> None:
        super().__init__(
            design_steps=_DESIGN_STEPS,
            implement_steps=_IMPLEMENT_STEPS,
            commit_steps=_COMMIT_STEPS,
            test_steps=_TEST_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
