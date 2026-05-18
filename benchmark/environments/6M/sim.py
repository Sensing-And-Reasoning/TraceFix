"""Codebase Development simulation config for task 6M."""

from benchmark.tools.sim_codebase_dev import (
    CodebaseDevSim,
    CodeReviewStep,
    ImplementStep,
    MergeStep,
    RunTestsStep,
    WriteTestsStep,
)

_RESOURCES = ["BUILD_SERVER", "REPO", "TEST_ENV"]

_IMPLEMENT_STEPS = [
    ImplementStep(agent_id="DEVELOPER_A", feature="user_authentication"),
    ImplementStep(agent_id="DEVELOPER_B", feature="payment_processing"),
]

_WRITE_TESTS_STEPS = [
    WriteTestsStep(agent_id="TEST_WRITER", component="user_authentication"),
    WriteTestsStep(agent_id="TEST_WRITER", component="payment_processing"),
]

_CODE_REVIEW_STEPS = [
    CodeReviewStep(agent_id="REVIEWER", target="user_authentication"),
    CodeReviewStep(agent_id="REVIEWER", target="payment_processing"),
]

_RUN_TESTS_STEPS = [
    RunTestsStep(agent_id="CI_RUNNER", suite="full_test_suite_after_auth"),
    RunTestsStep(agent_id="CI_RUNNER", suite="full_test_suite_after_payment"),
]

_MERGE_STEPS = [
    MergeStep(agent_id="DEVELOPER_A", branch="user_authentication"),
    MergeStep(agent_id="DEVELOPER_B", branch="payment_processing"),
]


class MultiFileFeatureDevSim(CodebaseDevSim):
    """6M: Two developers on features sharing multiple source files,
    with test writer, reviewer, and CI runner."""

    def __init__(self) -> None:
        super().__init__(
            implement_steps=_IMPLEMENT_STEPS,
            write_tests_steps=_WRITE_TESTS_STEPS,
            code_review_steps=_CODE_REVIEW_STEPS,
            run_tests_steps=_RUN_TESTS_STEPS,
            merge_steps=_MERGE_STEPS,
            resources=_RESOURCES,
        )
