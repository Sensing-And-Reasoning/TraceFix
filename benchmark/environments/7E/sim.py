"""Document co-authoring simulation config for task 7E."""

from benchmark.tools.sim_document import (
    CombineStep,
    DocumentSim,
    ReferencesStep,
    ReviewStep,
    ReviseStep,
    WriteSectionStep,
)

_RESOURCES = ["DOCUMENT"]

_WRITE_STEPS = [
    WriteSectionStep(agent_id="WRITER_A", section="CHAPTER_1"),
    WriteSectionStep(agent_id="WRITER_B", section="CHAPTER_2"),
]

_REVISE_STEPS = [
    ReviseStep(agent_id="WRITER_A", section="CHAPTER_1"),
    ReviseStep(agent_id="WRITER_B", section="CHAPTER_2"),
]

_REFERENCES_STEPS = [
    ReferencesStep(agent_id="WRITER_A", scope="CHAPTER_1"),
    ReferencesStep(agent_id="WRITER_B", scope="CHAPTER_2"),
]

_REVIEW_STEPS = [
    ReviewStep(agent_id="EDITOR", scope="CHAPTER_1"),
    ReviewStep(agent_id="EDITOR", scope="CHAPTER_2"),
]

_COMBINE_STEPS = [
    CombineStep(agent_id="EDITOR", sections=["CHAPTER_1", "CHAPTER_2"]),
]


class TwoAuthorDocumentSim(DocumentSim):
    """7E: Two writers co-authoring a two-chapter document with an editor.

    Decision tools: review_sections (EDITOR may request revision → writer revises
    and EDITOR re-reviews).  fact_check, peer_review, and make_editorial_decision
    are not used in this task, so they are excluded from _DECISION_TOOLS to
    prevent spurious failure injection.
    """

    _DECISION_TOOLS: dict = {
        "review_sections": 0.3,
    }

    def __init__(self) -> None:
        super().__init__(
            write_steps=_WRITE_STEPS,
            revise_steps=_REVISE_STEPS,
            references_steps=_REFERENCES_STEPS,
            review_steps=_REVIEW_STEPS,
            combine_steps=_COMBINE_STEPS,
            resources=_RESOURCES,
        )
