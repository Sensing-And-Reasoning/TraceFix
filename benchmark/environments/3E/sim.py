"""Research Writing simulation config for task 3E."""

import json
from pathlib import Path

from benchmark.tools.sim_research import (
    CombineStep,
    ReferencesStep,
    ResearchSim,
    ResearchStep,
    ReviewStep,
    ReviseStep,
    WriteSectionStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "3E" / "metadata.json").read_text()
)

_RESOURCES = ["DATABASE", "DOCUMENT"]

_RESEARCH_STEPS = [
    ResearchStep(agent_id="RESEARCHER_A", topic="subtopic_a"),
    ResearchStep(agent_id="RESEARCHER_B", topic="subtopic_b"),
]

_WRITE_STEPS = [
    WriteSectionStep(agent_id="RESEARCHER_A", section="section_a"),
    WriteSectionStep(agent_id="RESEARCHER_B", section="section_b"),
]

_REVISE_STEPS = [
    ReviseStep(agent_id="RESEARCHER_A", section="section_a"),
    ReviseStep(agent_id="RESEARCHER_B", section="section_b"),
]

_REFERENCES_STEPS = [
    ReferencesStep(agent_id="RESEARCHER_A", scope="section_a"),
    ReferencesStep(agent_id="RESEARCHER_B", scope="section_b"),
]

_REVIEW_STEPS = [
    ReviewStep(agent_id="EDITOR", scope="section_a"),
    ReviewStep(agent_id="EDITOR", scope="section_b"),
]

_COMBINE_STEPS = [
    CombineStep(agent_id="EDITOR", sections=["section_a", "section_b"]),
]


class TwoAuthorReportSim(ResearchSim):
    """3E: Two researchers and an editor collaborating on a report."""

    def __init__(self) -> None:
        super().__init__(
            research_steps=_RESEARCH_STEPS,
            write_steps=_WRITE_STEPS,
            revise_steps=_REVISE_STEPS,
            references_steps=_REFERENCES_STEPS,
            review_steps=_REVIEW_STEPS,
            combine_steps=_COMBINE_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
