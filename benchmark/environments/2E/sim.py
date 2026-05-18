"""Research Paper Writing simulation config for task 2E."""

import json
from pathlib import Path

from benchmark.tools.sim_smart_building import (
    DraftStep,
    ReadStep,
    ReviewStep,
    SmartBuildingSim,
    WriteStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "2E" / "metadata.json").read_text()
)

_RESOURCES = _METADATA["resources"]

_READ_STEPS = [
    ReadStep(agent_id="RESEARCHER_A", topic="intro_methods_connection"),
    ReadStep(agent_id="RESEARCHER_B", topic="methods_results_connection"),
    ReadStep(agent_id="RESEARCHER_C", topic="results_intro_analysis"),
]

_DRAFT_STEPS = [
    DraftStep(agent_id="RESEARCHER_A", section="sec_intro_methods"),
    DraftStep(agent_id="RESEARCHER_B", section="sec_methods_results"),
    DraftStep(agent_id="RESEARCHER_C", section="sec_results_intro"),
]

_WRITE_STEPS = [
    WriteStep(agent_id="RESEARCHER_A", sections=["INTRO_SECTION", "METHODS_SECTION"]),
    WriteStep(agent_id="RESEARCHER_B", sections=["METHODS_SECTION", "RESULTS_SECTION"]),
    WriteStep(agent_id="RESEARCHER_C", sections=["INTRO_SECTION", "RESULTS_SECTION"]),
]

_REVIEW_STEPS = [
    ReviewStep(agent_id="RESEARCHER_A", section="sec_intro_methods"),
    ReviewStep(agent_id="RESEARCHER_B", section="sec_methods_results"),
    ReviewStep(agent_id="RESEARCHER_C", section="sec_results_intro"),
]


class ResearchPaperSim(SmartBuildingSim):
    """2E: Three researchers co-authoring a paper with 3 sections.

    Review is terminal (pass or fail, no retry), so review_own_work is not
    a decision tool — failure injection via --scenario/--difficulty is disabled.
    """

    # No retry loop: review outcome is terminal regardless.
    # Overriding to empty prevents --scenario/--difficulty from injecting
    # failures that would leave _review_done permanently False.
    _DECISION_TOOLS: dict = {}

    def __init__(self) -> None:
        super().__init__(
            read_steps=_READ_STEPS,
            draft_steps=_DRAFT_STEPS,
            write_steps=_WRITE_STEPS,
            review_steps=_REVIEW_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
