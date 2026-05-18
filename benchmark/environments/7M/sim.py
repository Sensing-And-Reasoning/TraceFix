"""Document co-authoring simulation config for task 7M."""

from benchmark.tools.sim_document import (
    CombineStep,
    DocumentSim,
    FactCheckStep,
    FigureStep,
    InsertFigureStep,
    ReferencesStep,
    ReviewStep,
    ReviseStep,
    WriteSectionStep,
)

_RESOURCES = ["DOCUMENT", "FIGURE_STORE"]

_WRITE_STEPS = [
    WriteSectionStep(agent_id="WRITER_A", section="CHAPTER_1"),
    WriteSectionStep(agent_id="WRITER_A", section="CHAPTER_2"),
    WriteSectionStep(agent_id="WRITER_B", section="CHAPTER_3"),
]

_REVISE_STEPS = [
    ReviseStep(agent_id="WRITER_A", section="CHAPTER_1"),
    ReviseStep(agent_id="WRITER_A", section="CHAPTER_2"),
    ReviseStep(agent_id="WRITER_B", section="CHAPTER_3"),
]

_REFERENCES_STEPS = [
    ReferencesStep(agent_id="WRITER_A", scope="CHAPTER_1"),
    ReferencesStep(agent_id="WRITER_A", scope="CHAPTER_2"),
    ReferencesStep(agent_id="WRITER_B", scope="CHAPTER_3"),
]

# FACT_CHECKER handles 2 requests (one per writer, not per chapter)
_FACT_CHECK_STEPS = [
    FactCheckStep(agent_id="FACT_CHECKER", section="CHAPTERS_1_2"),
    FactCheckStep(agent_id="FACT_CHECKER", section="CHAPTER_3"),
]

# FIGURE_CREATOR handles 2 requests (one per writer)
_FIGURE_STEPS = [
    FigureStep(agent_id="FIGURE_CREATOR", figure_id="fig_ch1"),
    FigureStep(agent_id="FIGURE_CREATOR", figure_id="fig_ch3"),
]

_INSERT_FIGURE_STEPS = [
    InsertFigureStep(agent_id="FIGURE_CREATOR", figure_id="fig_ch1", section="CHAPTER_1"),
    InsertFigureStep(agent_id="FIGURE_CREATOR", figure_id="fig_ch3", section="CHAPTER_3"),
]

_REVIEW_STEPS = [
    ReviewStep(agent_id="EDITOR", scope="CHAPTER_1"),
    ReviewStep(agent_id="EDITOR", scope="CHAPTER_2"),
    ReviewStep(agent_id="EDITOR", scope="CHAPTER_3"),
]

_COMBINE_STEPS = [
    CombineStep(agent_id="EDITOR", sections=["CHAPTER_1", "CHAPTER_2", "CHAPTER_3"]),
]


class MultiAuthorFigureDocumentSim(DocumentSim):
    """7M: Two writers, figure creator, fact checker, and editor
    co-authoring a three-chapter document with figures.

    Decision tools: review_sections (EDITOR may request revision → retry) and
    fact_check (FACT_CHECKER may flag issues → writer revises → re-check).
    peer_review and make_editorial_decision are not used in this task.
    """

    _DECISION_TOOLS: dict = {
        "review_sections": 0.3,
        "fact_check": 0.2,
    }

    def __init__(self) -> None:
        super().__init__(
            write_steps=_WRITE_STEPS,
            revise_steps=_REVISE_STEPS,
            references_steps=_REFERENCES_STEPS,
            fact_check_steps=_FACT_CHECK_STEPS,
            figure_steps=_FIGURE_STEPS,
            insert_figure_steps=_INSERT_FIGURE_STEPS,
            review_steps=_REVIEW_STEPS,
            combine_steps=_COMBINE_STEPS,
            resources=_RESOURCES,
        )
