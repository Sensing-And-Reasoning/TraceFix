"""Code Collaboration simulation config for task 4M."""

import json
from pathlib import Path

from benchmark.tools.sim_code_collab import (
    CodeCollabSim,
    CodeReviewStep,
    DesignProposalStep,
    MergeStep,
    RefactorStep,
    RunTestsStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "4M" / "metadata.json").read_text()
)

_RESOURCES = ["REPO", "TEST_ENV"]

_DESIGN_PROPOSAL_STEPS = [
    DesignProposalStep(agent_id="ARCHITECT", proposal="module_a_refactor"),
    DesignProposalStep(agent_id="ARCHITECT", proposal="module_b_refactor"),
]

_REFACTOR_STEPS = [
    RefactorStep(agent_id="DEVELOPER_A", target="module_a"),
    RefactorStep(agent_id="DEVELOPER_B", target="module_b"),
    RefactorStep(agent_id="DEVELOPER_A", target="SHARED_LIBRARY"),
    RefactorStep(agent_id="DEVELOPER_B", target="SHARED_LIBRARY"),
]

_CODE_REVIEW_STEPS = [
    CodeReviewStep(agent_id="REVIEWER", target="module_a"),
    CodeReviewStep(agent_id="REVIEWER", target="module_b"),
]

_RUN_TESTS_STEPS = [
    RunTestsStep(agent_id="TESTER", suite="module_a_tests"),
    RunTestsStep(agent_id="TESTER", suite="module_b_tests"),
]

_MERGE_STEPS = [
    MergeStep(agent_id="DEVELOPER_A", branch="module_a"),
    MergeStep(agent_id="DEVELOPER_B", branch="module_b"),
]


class SharedLibraryRefactorSim(CodeCollabSim):
    """4M: Two developers refactoring modules with shared library,
    architect approval, code review, and testing.

    Tests and code reviews are terminal (pass or fail, no retry loop), so
    run_tests and code_review are not decision tools.  Overriding to empty
    prevents --scenario/--difficulty from injecting failures that would leave
    completion flags permanently False.
    """

    # No retry loop: test and review outcomes are terminal.
    _DECISION_TOOLS: dict = {}

    def __init__(self) -> None:
        super().__init__(
            design_proposal_steps=_DESIGN_PROPOSAL_STEPS,
            refactor_steps=_REFACTOR_STEPS,
            code_review_steps=_CODE_REVIEW_STEPS,
            run_tests_steps=_RUN_TESTS_STEPS,
            merge_steps=_MERGE_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
