"""Document co-authoring simulation config for task 7H."""

from benchmark.tools.sim_document import (
    CombineStep,
    DocumentSim,
    EditorialStep,
    FactCheckStep,
    FigureStep,
    InsertFigureStep,
    ReferencesStep,
    ReviewStep,
    ReviseStep,
    WriteSectionStep,
)

_RESOURCES = ["DOCUMENT", "FIGURE_STORE"]

# WRITER_A writes chapter_1 and chapter_2 (Part I) as separate sections
_WRITE_STEPS = [
    WriteSectionStep(agent_id="WRITER_A", section="CHAPTER_1"),
    WriteSectionStep(agent_id="WRITER_A", section="CHAPTER_2"),
    WriteSectionStep(agent_id="WRITER_B", section="CHAPTER_3"),
    WriteSectionStep(agent_id="WRITER_C", section="CHAPTER_4"),
]

_REVISE_STEPS = [
    ReviseStep(agent_id="WRITER_A", section="CHAPTER_1"),
    ReviseStep(agent_id="WRITER_A", section="CHAPTER_2"),
    ReviseStep(agent_id="WRITER_B", section="CHAPTER_3"),
    ReviseStep(agent_id="WRITER_C", section="CHAPTER_4"),
]

# WRITER_A updates refs for chapter_1 and chapter_2 separately
_REFERENCES_STEPS = [
    ReferencesStep(agent_id="WRITER_A", scope="CHAPTER_1"),
    ReferencesStep(agent_id="WRITER_A", scope="CHAPTER_2"),
    ReferencesStep(agent_id="WRITER_B", scope="CHAPTER_3"),
    ReferencesStep(agent_id="WRITER_C", scope="CHAPTER_4"),
]

_FACT_CHECK_STEPS = [
    FactCheckStep(agent_id="FACT_CHECKER", section="CHAPTERS_1_2"),
    FactCheckStep(agent_id="FACT_CHECKER", section="CHAPTER_3"),
    FactCheckStep(agent_id="FACT_CHECKER", section="CHAPTER_4"),
]

# REVIEWER calls review_sections (not peer_review)
_REVIEW_STEPS = [
    ReviewStep(agent_id="REVIEWER", scope="CHAPTERS_1_2"),
    ReviewStep(agent_id="REVIEWER", scope="CHAPTER_3"),
    ReviewStep(agent_id="REVIEWER", scope="CHAPTER_4"),
]

_FIGURE_STEPS = [
    FigureStep(agent_id="FIGURE_CREATOR", figure_id="fig_part_1"),
    FigureStep(agent_id="FIGURE_CREATOR", figure_id="fig_ch3"),
    FigureStep(agent_id="FIGURE_CREATOR", figure_id="fig_ch4"),
]

_INSERT_FIGURE_STEPS = [
    InsertFigureStep(agent_id="FIGURE_CREATOR", figure_id="fig_part_1", section="CHAPTER_1"),
    InsertFigureStep(agent_id="FIGURE_CREATOR", figure_id="fig_ch3", section="CHAPTER_3"),
    InsertFigureStep(agent_id="FIGURE_CREATOR", figure_id="fig_ch4", section="CHAPTER_4"),
]

# EIC calls make_editorial_decision once and combine_sections once
_EDITORIAL_STEPS = [
    EditorialStep(agent_id="EDITOR_IN_CHIEF", decision_type="final"),
]

_COMBINE_STEPS = [
    CombineStep(agent_id="EDITOR_IN_CHIEF", sections=["CHAPTER_1", "CHAPTER_2", "CHAPTER_3", "CHAPTER_4"]),
]


class LargeCollaborativeDocumentSim(DocumentSim):
    """7H: Three writers, figure creator, fact checker, reviewer, and
    editor-in-chief co-authoring a four-chapter document in two parts.

    Decision tools: review_sections (REVIEWER may request major/minor revision
    → retry on major), fact_check (FACT_CHECKER may flag issues → retry), and
    make_editorial_decision (EDITOR_IN_CHIEF may reject → retry).
    peer_review is not tracked by this sim (REVIEWER uses review_sections).
    """

    _DECISION_TOOLS: dict = {
        "review_sections": 0.3,
        "fact_check": 0.2,
        "make_editorial_decision": 0.3,
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
            editorial_steps=_EDITORIAL_STEPS,
            combine_steps=_COMBINE_STEPS,
            resources=_RESOURCES,
        )
