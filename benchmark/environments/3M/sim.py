"""Research Writing simulation config for task 3M."""

import json
from pathlib import Path

from benchmark.tools.sim_research import (
    CombineStep,
    EditorialStep,
    FactCheckStep,
    ReferencesStep,
    ResearchSim,
    ResearchStep,
    ReviewStep,
    ReviseStep,
    WriteSectionStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "3M" / "metadata.json").read_text()
)

_RESOURCES = ["DATABASE", "DOCUMENT"]

_RESEARCH_STEPS = [
    ResearchStep(agent_id="RESEARCHER_A", topic="subtopic_a"),
    ResearchStep(agent_id="RESEARCHER_B", topic="subtopic_b"),
    ResearchStep(agent_id="RESEARCHER_C", topic="subtopic_c"),
]

_WRITE_STEPS = [
    WriteSectionStep(agent_id="RESEARCHER_A", section="section_a"),
    WriteSectionStep(agent_id="RESEARCHER_B", section="section_b"),
    WriteSectionStep(agent_id="RESEARCHER_C", section="section_c"),
]

_REVISE_STEPS = [
    ReviseStep(agent_id="RESEARCHER_A", section="section_a"),
    ReviseStep(agent_id="RESEARCHER_B", section="section_b"),
    ReviseStep(agent_id="RESEARCHER_C", section="section_c"),
]

_REFERENCES_STEPS = [
    ReferencesStep(agent_id="RESEARCHER_A", scope="section_a"),
    ReferencesStep(agent_id="RESEARCHER_B", scope="section_b"),
    ReferencesStep(agent_id="RESEARCHER_C", scope="section_c"),
]

_FACT_CHECK_STEPS = [
    FactCheckStep(agent_id="FACT_CHECKER", section="section_a"),
    FactCheckStep(agent_id="FACT_CHECKER", section="section_b"),
    FactCheckStep(agent_id="FACT_CHECKER", section="section_c"),
]

_REVIEW_STEPS = [
    ReviewStep(agent_id="EDITOR", scope="section_a"),
    ReviewStep(agent_id="EDITOR", scope="section_b"),
    ReviewStep(agent_id="EDITOR", scope="section_c"),
]

_EDITORIAL_STEPS: list[EditorialStep] = [
    # EDITOR's tools.json has no make_editorial_decision — finalize is
    # implicit when EDITOR calls combine_sections.
]

_COMBINE_STEPS = [
    CombineStep(agent_id="EDITOR", sections=["section_a", "section_b", "section_c"]),
]


class MultiAuthorPaperSim(ResearchSim):
    """3M: Three researchers, a fact checker, and an editor writing a paper."""

    def __init__(self) -> None:
        super().__init__(
            research_steps=_RESEARCH_STEPS,
            write_steps=_WRITE_STEPS,
            revise_steps=_REVISE_STEPS,
            references_steps=_REFERENCES_STEPS,
            fact_check_steps=_FACT_CHECK_STEPS,
            review_steps=_REVIEW_STEPS,
            editorial_steps=_EDITORIAL_STEPS,
            combine_steps=_COMBINE_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
