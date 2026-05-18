"""Research Paper Writing simulation config for task 2M."""

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
     / "descriptions" / "2M" / "metadata.json").read_text()
)

_RESOURCES = _METADATA["resources"]

_READ_STEPS = [
    ReadStep(agent_id="RESEARCHER_A", topic="intro_background_connection"),
    ReadStep(agent_id="RESEARCHER_B", topic="background_methods_connection"),
    ReadStep(agent_id="RESEARCHER_C", topic="methods_experiments_connection"),
    ReadStep(agent_id="RESEARCHER_D", topic="experiments_results_connection"),
    ReadStep(agent_id="RESEARCHER_E", topic="results_intro_analysis"),
]

_DRAFT_STEPS = [
    DraftStep(agent_id="RESEARCHER_A", section="sec_intro_background"),
    DraftStep(agent_id="RESEARCHER_B", section="sec_background_methods"),
    DraftStep(agent_id="RESEARCHER_C", section="sec_methods_experiments"),
    DraftStep(agent_id="RESEARCHER_D", section="sec_experiments_results"),
    DraftStep(agent_id="RESEARCHER_E", section="sec_results_intro"),
]

_WRITE_STEPS = [
    WriteStep(agent_id="RESEARCHER_A", sections=["BACKGROUND_SECTION", "INTRO_SECTION"]),
    WriteStep(agent_id="RESEARCHER_B", sections=["BACKGROUND_SECTION", "METHODS_SECTION"]),
    WriteStep(agent_id="RESEARCHER_C", sections=["EXPERIMENTS_SECTION", "METHODS_SECTION"]),
    WriteStep(agent_id="RESEARCHER_D", sections=["EXPERIMENTS_SECTION", "RESULTS_SECTION"]),
    WriteStep(agent_id="RESEARCHER_E", sections=["INTRO_SECTION", "RESULTS_SECTION"]),
]

_REVIEW_STEPS = [
    ReviewStep(agent_id="RESEARCHER_A", section="sec_intro_background"),
    ReviewStep(agent_id="RESEARCHER_B", section="sec_background_methods"),
    ReviewStep(agent_id="RESEARCHER_C", section="sec_methods_experiments"),
    ReviewStep(agent_id="RESEARCHER_D", section="sec_experiments_results"),
    ReviewStep(agent_id="RESEARCHER_E", section="sec_results_intro"),
]


class ResearchPaperSim(SmartBuildingSim):
    """2M: Five researchers co-authoring a paper with 5 sections.

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
