"""Codebase Development simulation config for task 6E."""

from benchmark.tools.sim_codebase_dev import (
    CodebaseDevSim,
    CodeReviewStep,
    ImplementStep,
    MergeStep,
)

_RESOURCES = ["REPO"]

_IMPLEMENT_STEPS = [
    ImplementStep(agent_id="DEVELOPER_A", feature="user_authentication"),
    ImplementStep(agent_id="DEVELOPER_B", feature="notification_feature"),
]

_CODE_REVIEW_STEPS = [
    CodeReviewStep(agent_id="REVIEWER", target="user_authentication"),
    CodeReviewStep(agent_id="REVIEWER", target="notification_feature"),
]

_MERGE_STEPS = [
    MergeStep(agent_id="DEVELOPER_A", branch="dev_a_feature"),
    MergeStep(agent_id="DEVELOPER_B", branch="dev_b_feature"),
]


class SharedUtilityFileSim(CodebaseDevSim):
    """6E: Two developers modifying a shared utility file with code review
    and sequential merges."""

    def __init__(self) -> None:
        super().__init__(
            implement_steps=_IMPLEMENT_STEPS,
            code_review_steps=_CODE_REVIEW_STEPS,
            merge_steps=_MERGE_STEPS,
            resources=_RESOURCES,
        )
