"""Codebase Development simulation config for task 6H."""

from benchmark.tools.sim_codebase_dev import (
    CodebaseDevSim,
    CodeReviewStep,
    DeployStep,
    ImplementStep,
    MergeStep,
    RollbackStep,
    RunTestsStep,
    ValidateStagingStep,
    WriteTestsStep,
)

_RESOURCES = ["BUILD_SERVER", "REPO", "STAGING_ENV", "TEST_ENV"]

_IMPLEMENT_STEPS = [
    ImplementStep(agent_id="DEVELOPER_A", feature="user_authentication"),
    ImplementStep(agent_id="DEVELOPER_B", feature="payment_processing"),
    ImplementStep(agent_id="DEVELOPER_C", feature="notification_system"),
]

_WRITE_TESTS_STEPS = [
    WriteTestsStep(agent_id="TEST_WRITER", component="user_authentication"),
    WriteTestsStep(agent_id="TEST_WRITER", component="payment_processing"),
    WriteTestsStep(agent_id="TEST_WRITER", component="notification_system"),
]

_CODE_REVIEW_STEPS = [
    CodeReviewStep(agent_id="REVIEWER", target="user_authentication"),
    CodeReviewStep(agent_id="REVIEWER", target="payment_processing"),
    CodeReviewStep(agent_id="REVIEWER", target="notification_system"),
]

_RUN_TESTS_STEPS = [
    RunTestsStep(agent_id="CI_RUNNER", suite="full_suite_after_auth"),
    RunTestsStep(agent_id="CI_RUNNER", suite="full_suite_after_payment"),
    RunTestsStep(agent_id="CI_RUNNER", suite="full_suite_after_notification"),
]

_MERGE_STEPS = [
    MergeStep(agent_id="DEVELOPER_A", branch="user_authentication"),
    MergeStep(agent_id="DEVELOPER_B", branch="payment_processing"),
    MergeStep(agent_id="DEVELOPER_C", branch="notification_system"),
]

_DEPLOY_STEPS = [
    DeployStep(agent_id="RELEASE_MANAGER", service="user_authentication"),
    DeployStep(agent_id="RELEASE_MANAGER", service="payment_processing"),
    DeployStep(agent_id="RELEASE_MANAGER", service="notification_system"),
]

_VALIDATE_STAGING_STEPS = [
    ValidateStagingStep(agent_id="RELEASE_MANAGER", service="user_authentication"),
    ValidateStagingStep(agent_id="RELEASE_MANAGER", service="payment_processing"),
    ValidateStagingStep(agent_id="RELEASE_MANAGER", service="notification_system"),
]

_ROLLBACK_STEPS = [
    RollbackStep(agent_id="RELEASE_MANAGER", service="user_authentication"),
    RollbackStep(agent_id="RELEASE_MANAGER", service="payment_processing"),
    RollbackStep(agent_id="RELEASE_MANAGER", service="notification_system"),
]


class StagedIntegrationSim(CodebaseDevSim):
    """6H: Three developers on features with staged integration --
    test writer, reviewer, CI runner, and release manager."""

    def __init__(self) -> None:
        super().__init__(
            implement_steps=_IMPLEMENT_STEPS,
            write_tests_steps=_WRITE_TESTS_STEPS,
            code_review_steps=_CODE_REVIEW_STEPS,
            run_tests_steps=_RUN_TESTS_STEPS,
            merge_steps=_MERGE_STEPS,
            deploy_steps=_DEPLOY_STEPS,
            validate_staging_steps=_VALIDATE_STAGING_STEPS,
            rollback_steps=_ROLLBACK_STEPS,
            resources=_RESOURCES,
        )
