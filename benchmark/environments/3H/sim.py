"""Research Writing simulation config for task 3H."""

import json
from pathlib import Path

from benchmark.tools.sim_research import (
    CombineStep,
    EditorialStep,
    FigureStep,
    InsertFigureStep,
    PeerReviewStep,
    ReferencesStep,
    ResearchSim,
    ResearchStep,
    ReviseStep,
    WriteSectionStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "3H" / "metadata.json").read_text()
)

_RESOURCES = [
    "DATABASE",
    "FIGURE_REPOSITORY",
    "SECTION_A",
    "SECTION_B",
    "SECTION_C",
    "SECTION_D",
]

_RESEARCH_STEPS = [
    ResearchStep(agent_id="RESEARCHER_A", topic="subtopic_a"),
    ResearchStep(agent_id="RESEARCHER_B", topic="subtopic_b"),
    ResearchStep(agent_id="RESEARCHER_C", topic="subtopic_c"),
    ResearchStep(agent_id="RESEARCHER_D", topic="subtopic_d"),
]

_WRITE_STEPS = [
    WriteSectionStep(agent_id="RESEARCHER_A", section="section_a"),
    WriteSectionStep(agent_id="RESEARCHER_B", section="section_b"),
    WriteSectionStep(agent_id="RESEARCHER_C", section="section_c"),
    WriteSectionStep(agent_id="RESEARCHER_D", section="section_d"),
]

_REVISE_STEPS = [
    ReviseStep(agent_id="RESEARCHER_A", section="section_a"),
    ReviseStep(agent_id="RESEARCHER_B", section="section_b"),
    ReviseStep(agent_id="RESEARCHER_C", section="section_c"),
    ReviseStep(agent_id="RESEARCHER_D", section="section_d"),
]

_REFERENCES_STEPS = [
    ReferencesStep(agent_id="RESEARCHER_A", scope="section_a"),
    ReferencesStep(agent_id="RESEARCHER_B", scope="section_b"),
    ReferencesStep(agent_id="RESEARCHER_C", scope="section_c"),
    ReferencesStep(agent_id="RESEARCHER_D", scope="section_d"),
]

_FIGURE_STEPS = [
    FigureStep(agent_id="DATA_ANALYST", figure_id="fig_a"),
    FigureStep(agent_id="DATA_ANALYST", figure_id="fig_b"),
    FigureStep(agent_id="DATA_ANALYST", figure_id="fig_c"),
    FigureStep(agent_id="DATA_ANALYST", figure_id="fig_d"),
]

_INSERT_FIGURE_STEPS = [
    InsertFigureStep(agent_id="DATA_ANALYST", figure_id="fig_a", section="section_a"),
    InsertFigureStep(agent_id="DATA_ANALYST", figure_id="fig_b", section="section_b"),
    InsertFigureStep(agent_id="DATA_ANALYST", figure_id="fig_c", section="section_c"),
    InsertFigureStep(agent_id="DATA_ANALYST", figure_id="fig_d", section="section_d"),
]

_PEER_REVIEW_STEPS = [
    PeerReviewStep(agent_id="REVIEWER", section="section_a"),
    PeerReviewStep(agent_id="REVIEWER", section="section_b"),
    PeerReviewStep(agent_id="REVIEWER", section="section_c"),
    PeerReviewStep(agent_id="REVIEWER", section="section_d"),
]

_EDITORIAL_STEPS = [
    EditorialStep(agent_id="EDITOR_IN_CHIEF", decision_type="finalize"),
]

_COMBINE_STEPS = [
    CombineStep(
        agent_id="EDITOR_IN_CHIEF",
        sections=["section_a", "section_b", "section_c", "section_d"],
    ),
]


class LargeSurveyPaperSim(ResearchSim):
    """3H: Four researchers, data analyst, reviewer, and editor-in-chief
    producing a comprehensive survey paper.

    Editorial decisions are terminal (EDITOR_IN_CHIEF decides once, no retry
    on failure), so make_editorial_decision is not a decision tool.
    """

    # No retry loop for editorial decisions: outcome is terminal.
    _DECISION_TOOLS: dict = {
        "peer_review": 0.2,
    }

    def __init__(self) -> None:
        super().__init__(
            research_steps=_RESEARCH_STEPS,
            write_steps=_WRITE_STEPS,
            revise_steps=_REVISE_STEPS,
            references_steps=_REFERENCES_STEPS,
            figure_steps=_FIGURE_STEPS,
            insert_figure_steps=_INSERT_FIGURE_STEPS,
            peer_review_steps=_PEER_REVIEW_STEPS,
            editorial_steps=_EDITORIAL_STEPS,
            combine_steps=_COMBINE_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
