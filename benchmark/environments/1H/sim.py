"""Shared Codebase Development simulation config for task 1H."""

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
     / "descriptions" / "1H" / "metadata.json").read_text()
)

_RESOURCES = ["AUTH_MODULE", "DATABASE_MODULE", "API_MODULE", "PAYMENT_MODULE", "NOTIFY_MODULE", "ANALYTICS_MODULE", "SEARCH_MODULE"]

_DESIGN_STEPS = [
    DesignStep(agent_id="DEVELOPER_A", feature="user_authentication"),
    DesignStep(agent_id="DEVELOPER_B", feature="rest_api_endpoints"),
    DesignStep(agent_id="DEVELOPER_C", feature="payment_system"),
    DesignStep(agent_id="DEVELOPER_D", feature="notification_service"),
    DesignStep(agent_id="DEVELOPER_E", feature="data_analytics"),
    DesignStep(agent_id="DEVELOPER_F", feature="search_engine"),
    DesignStep(agent_id="DEVELOPER_G", feature="admin_panel"),
]

_IMPLEMENT_STEPS = [
    ImplementStep(agent_id="DEVELOPER_A", feature="user_authentication"),
    ImplementStep(agent_id="DEVELOPER_B", feature="rest_api_endpoints"),
    ImplementStep(agent_id="DEVELOPER_C", feature="payment_system"),
    ImplementStep(agent_id="DEVELOPER_D", feature="notification_service"),
    ImplementStep(agent_id="DEVELOPER_E", feature="data_analytics"),
    ImplementStep(agent_id="DEVELOPER_F", feature="search_engine"),
    ImplementStep(agent_id="DEVELOPER_G", feature="admin_panel"),
]

_COMMIT_STEPS = [
    CommitStep(agent_id="DEVELOPER_A", modules=["AUTH_MODULE", "DATABASE_MODULE"]),
    CommitStep(agent_id="DEVELOPER_B", modules=["API_MODULE", "DATABASE_MODULE"]),
    CommitStep(agent_id="DEVELOPER_C", modules=["API_MODULE", "PAYMENT_MODULE"]),
    CommitStep(agent_id="DEVELOPER_D", modules=["NOTIFY_MODULE", "PAYMENT_MODULE"]),
    CommitStep(agent_id="DEVELOPER_E", modules=["ANALYTICS_MODULE", "NOTIFY_MODULE"]),
    CommitStep(agent_id="DEVELOPER_F", modules=["ANALYTICS_MODULE", "SEARCH_MODULE"]),
    CommitStep(agent_id="DEVELOPER_G", modules=["AUTH_MODULE", "SEARCH_MODULE"]),
]

_TEST_STEPS = [
    TestStep(agent_id="DEVELOPER_A", feature="user_authentication"),
    TestStep(agent_id="DEVELOPER_B", feature="rest_api_endpoints"),
    TestStep(agent_id="DEVELOPER_C", feature="payment_system"),
    TestStep(agent_id="DEVELOPER_D", feature="notification_service"),
    TestStep(agent_id="DEVELOPER_E", feature="data_analytics"),
    TestStep(agent_id="DEVELOPER_F", feature="search_engine"),
    TestStep(agent_id="DEVELOPER_G", feature="admin_panel"),
]


class SharedCodebaseSim(CodingSim):
    """1H: Seven developers on independent features in a shared codebase."""

    def __init__(self) -> None:
        super().__init__(
            design_steps=_DESIGN_STEPS,
            implement_steps=_IMPLEMENT_STEPS,
            commit_steps=_COMMIT_STEPS,
            test_steps=_TEST_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
