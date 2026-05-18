"""Parameterized document co-authoring simulation (scenarios 7E/7M/7H)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._base import ToolResult
from .sim_base import SimContext


@dataclass
class WriteSectionStep:
    """A section writing step."""

    agent_id: str
    section: str


@dataclass
class ReviseStep:
    """A section revision step."""

    agent_id: str
    section: str


@dataclass
class ReferencesStep:
    """A references update step."""

    agent_id: str
    scope: str


@dataclass
class ReviewStep:
    """A review step."""

    agent_id: str
    scope: str


@dataclass
class FactCheckStep:
    """A fact-checking step."""

    agent_id: str
    section: str


@dataclass
class PeerReviewStep:
    """A peer review step."""

    agent_id: str
    section: str


@dataclass
class FigureStep:
    """A figure creation step."""

    agent_id: str
    figure_id: str


@dataclass
class InsertFigureStep:
    """A figure insertion step."""

    agent_id: str
    figure_id: str
    section: str


@dataclass
class CombineStep:
    """A sections combination step."""

    agent_id: str
    sections: list[str]


@dataclass
class EditorialStep:
    """An editorial decision step."""

    agent_id: str
    decision_type: str


class DocumentSim(SimContext):
    """Simulation for collaborative document co-authoring.

    Tracks per-agent progress through writing, revision, review, figure
    creation, and editorial phases.  Detects resource-hold violations for
    document and figure_store access.

    Args:
        write_steps: Section writing steps (need document).
        revise_steps: Section revision steps (need document).
        references_steps: Reference update steps.
        review_steps: Review steps.
        fact_check_steps: Fact-checking steps.
        peer_review_steps: Peer review steps.
        figure_steps: Figure creation steps (need figure_store).
        insert_figure_steps: Figure insertion steps (need document + figure_store).
        combine_steps: Sections combination steps (need document).
        editorial_steps: Editorial decision steps.
        resources: List of shared resource names.
    """

    def __init__(
        self,
        write_steps: list[WriteSectionStep] | None = None,
        revise_steps: list[ReviseStep] | None = None,
        references_steps: list[ReferencesStep] | None = None,
        review_steps: list[ReviewStep] | None = None,
        fact_check_steps: list[FactCheckStep] | None = None,
        peer_review_steps: list[PeerReviewStep] | None = None,
        figure_steps: list[FigureStep] | None = None,
        insert_figure_steps: list[InsertFigureStep] | None = None,
        combine_steps: list[CombineStep] | None = None,
        editorial_steps: list[EditorialStep] | None = None,
        resources: list[str] | None = None,
    ) -> None:
        super().__init__()

        self._write_steps = {f"{s.agent_id}_{s.section}": s for s in (write_steps or [])}
        self._revise_steps = {f"{s.agent_id}_{s.section}": s for s in (revise_steps or [])}
        self._references_steps = {f"{s.agent_id}_{s.scope}": s for s in (references_steps or [])}
        self._review_steps = {f"{s.agent_id}_{s.scope}": s for s in (review_steps or [])}
        self._fact_check_steps = {f"{s.agent_id}_{s.section}": s for s in (fact_check_steps or [])}
        self._peer_review_steps = {f"{s.agent_id}_{s.section}": s for s in (peer_review_steps or [])}
        self._figure_steps = {f"{s.agent_id}_{s.figure_id}": s for s in (figure_steps or [])}
        self._insert_figure_steps = {f"{s.agent_id}_{s.figure_id}": s for s in (insert_figure_steps or [])}
        self._combine_steps = {f"{s.agent_id}_{'_'.join(sorted(s.sections))}": s for s in (combine_steps or [])}
        self._editorial_steps = {f"{s.agent_id}_{s.decision_type}": s for s in (editorial_steps or [])}

        self._write_done: dict[str, bool] = {k: False for k in self._write_steps}
        self._revise_done: dict[str, bool] = {k: False for k in self._revise_steps}
        self._references_done: dict[str, bool] = {k: False for k in self._references_steps}
        self._review_done: dict[str, bool] = {k: False for k in self._review_steps}
        self._fact_check_done: dict[str, bool] = {k: False for k in self._fact_check_steps}
        self._peer_review_done: dict[str, bool] = {k: False for k in self._peer_review_steps}
        self._figure_done: dict[str, bool] = {k: False for k in self._figure_steps}
        self._insert_figure_done: dict[str, bool] = {k: False for k in self._insert_figure_steps}
        self._combine_done: dict[str, bool] = {k: False for k in self._combine_steps}
        self._editorial_done: dict[str, bool] = {k: False for k in self._editorial_steps}

        for res in (resources or []):
            self.init_resource(res)

    # -- Decision tools (probabilistic failure for either/or branches) --

    _DECISION_TOOLS: dict[str, float] = {
        "review_sections": 0.3,
        "fact_check": 0.2,
        "peer_review": 0.2,
        "make_editorial_decision": 0.3,
    }

    # -- Resource requirements --

    _TOOL_RESOURCES: dict[str, list[str]] = {
        "write_section": ["DOCUMENT"],
        "revise_section": ["DOCUMENT"],
        "update_references": [],
        "review_sections": [],
        "fact_check": [],
        "peer_review": [],
        "create_figure": ["FIGURE_STORE"],
        "insert_figure": ["DOCUMENT", "FIGURE_STORE"],
        "combine_sections": ["DOCUMENT"],
        "make_editorial_decision": [],
    }

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        return list(self._TOOL_RESOURCES.get(tool_name, []))

    # -- Simulated delays --

    _TOOL_DELAYS: dict[str, tuple[float, float]] = {
        "write_section": (1.5, 4.0),
        "revise_section": (1.0, 3.0),
        "update_references": (0.5, 1.5),
        "review_sections": (1.0, 2.0),
        "fact_check": (1.0, 2.5),
        "peer_review": (1.5, 3.0),
        "create_figure": (1.0, 2.0),
        "insert_figure": (0.5, 1.0),
        "combine_sections": (1.0, 2.0),
        "make_editorial_decision": (0.5, 1.5),
    }

    def tool_delay(self, tool_name: str, **kwargs: Any) -> tuple[float, float]:
        return self._TOOL_DELAYS.get(tool_name, (0.0, 0.0))

    # -- Tool implementations --

    def write_section(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Write a section. Requires holding document."""
        section = self._get_param(kwargs, "section_name", "section")

        key = self._match_key(self._write_done, agent_id, section)
        if key in self._write_done:
            self._write_done[key] = True

        result = {"section": section, "status": "written", "agent": agent_id}
        self.log_event(agent_id, "write_section", {"section": section},
                       success=True, result=result)
        return ToolResult(tool_name="write_section", success=True,
                          data=result, message=f"Wrote section: {section}")

    def revise_section(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Revise a section. Requires holding document."""
        section = self._get_param(kwargs, "section_name", "section")

        key = self._match_key(self._revise_done, agent_id, section)
        if key in self._revise_done:
            self._revise_done[key] = True

        result = {"section": section, "status": "revised", "agent": agent_id}
        self.log_event(agent_id, "revise_section", {"section": section},
                       success=True, result=result)
        return ToolResult(tool_name="revise_section", success=True,
                          data=result, message=f"Revised section: {section}")

    def update_references(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Update references. No resource required."""
        scope = self._get_param(kwargs, "section_name", "scope")

        key = self._match_key(self._references_done, agent_id, scope)
        if key in self._references_done:
            self._references_done[key] = True

        result = {"scope": scope, "status": "references updated", "agent": agent_id}
        self.log_event(agent_id, "update_references", {"scope": scope},
                       success=True, result=result)
        return ToolResult(tool_name="update_references", success=True,
                          data=result, message=f"Updated references: {scope}")

    def review_sections(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Review sections. No resource required."""
        scope = self._get_param(kwargs, "section_name", "scope")

        key = self._match_key(self._review_done, agent_id, scope)

        if self.should_fail("review_sections", agent_id):
            result = {"scope": scope, "status": "needs_revision", "agent": agent_id}
            self.log_event(agent_id, "review_sections", {"scope": scope},
                           success=False, result=result)
            return ToolResult(tool_name="review_sections", success=False,
                              data=result, message=f"Review found issues: {scope}")

        if key in self._review_done:
            self._review_done[key] = True

        result = {"scope": scope, "status": "reviewed", "agent": agent_id}
        self.log_event(agent_id, "review_sections", {"scope": scope},
                       success=True, result=result)
        return ToolResult(tool_name="review_sections", success=True,
                          data=result, message=f"Reviewed sections: {scope}")

    def fact_check(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Fact-check a section. No resource required."""
        section = self._get_param(kwargs, "section", "section_name")

        if self.should_fail("fact_check", agent_id):
            result = {"section": section, "status": "issues_found", "agent": agent_id}
            self.log_event(agent_id, "fact_check", {"section": section},
                           success=False, result=result)
            return ToolResult(tool_name="fact_check", success=False,
                              data=result, message=f"Fact check found issues: {section}")

        self._mark_done(self._fact_check_done, agent_id, section)

        result = {"section": section, "status": "fact checked", "agent": agent_id}
        self.log_event(agent_id, "fact_check", {"section": section},
                       success=True, result=result)
        return ToolResult(tool_name="fact_check", success=True,
                          data=result, message=f"Fact checked: {section}")

    def peer_review(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Peer review a section. No resource required."""
        section = self._get_param(kwargs, "section", "manuscript", "section_name")

        if self.should_fail("peer_review", agent_id):
            result = {"section": section, "status": "revision_requested", "agent": agent_id}
            self.log_event(agent_id, "peer_review", {"section": section},
                           success=False, result=result)
            return ToolResult(tool_name="peer_review", success=False,
                              data=result, message=f"Peer review requests revision: {section}")

        self._mark_done(self._peer_review_done, agent_id, section)

        result = {"section": section, "status": "peer reviewed", "agent": agent_id}
        self.log_event(agent_id, "peer_review", {"section": section},
                       success=True, result=result)
        return ToolResult(tool_name="peer_review", success=True,
                          data=result, message=f"Peer reviewed: {section}")

    def create_figure(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Create a figure. Requires holding figure_store."""
        figure_id = self._get_param(kwargs, "figure_id", "description")

        self._mark_done(self._figure_done, agent_id, figure_id)

        result = {"figure_id": figure_id, "status": "created", "agent": agent_id}
        self.log_event(agent_id, "create_figure", {"figure_id": figure_id},
                       success=True, result=result)
        return ToolResult(tool_name="create_figure", success=True,
                          data=result, message=f"Created figure: {figure_id}")

    def insert_figure(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Insert a figure into the document. Requires holding document and figure_store."""
        figure_id = self._get_param(kwargs, "figure_id")
        section = self._get_param(kwargs, "section", "section_name")

        self._mark_done(self._insert_figure_done, agent_id, figure_id)

        result = {"figure_id": figure_id, "section": section, "status": "inserted", "agent": agent_id}
        self.log_event(agent_id, "insert_figure", {"figure_id": figure_id, "section": section},
                       success=True, result=result)
        return ToolResult(tool_name="insert_figure", success=True,
                          data=result, message=f"Inserted figure {figure_id} into {section}")

    def combine_sections(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Combine sections into final document. Requires holding document."""
        sections = self._parse_list(kwargs.get("sections", []))

        key = f"{agent_id}_{'_'.join(sorted(sections))}" if sections else f"{agent_id}_all"
        if key not in self._combine_done:
            key = self._match_key(self._combine_done, agent_id, "_".join(sorted(sections))) if sections else f"{agent_id}_all"
        if key in self._combine_done:
            self._combine_done[key] = True

        result = {"sections": sections, "status": "combined", "agent": agent_id}
        self.log_event(agent_id, "combine_sections", {"sections": sections},
                       success=True, result=result)
        return ToolResult(tool_name="combine_sections", success=True,
                          data=result, message=f"Combined sections: {', '.join(sections) if sections else 'all'}")

    def make_editorial_decision(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Make an editorial decision. No resource required."""
        decision_type = self._get_param(kwargs, "decision_type", "review_summary")

        if self.should_fail("make_editorial_decision", agent_id):
            result = {"decision_type": decision_type, "status": "rejected", "agent": agent_id}
            self.log_event(agent_id, "make_editorial_decision", {"decision_type": decision_type},
                           success=False, result=result)
            return ToolResult(tool_name="make_editorial_decision", success=False,
                              data=result, message=f"Editorial decision rejected: {decision_type}")

        self._mark_done(self._editorial_done, agent_id, decision_type)

        result = {"decision_type": decision_type, "status": "decided", "agent": agent_id}
        self.log_event(agent_id, "make_editorial_decision", {"decision_type": decision_type},
                       success=True, result=result)
        return ToolResult(tool_name="make_editorial_decision", success=True,
                          data=result, message=f"Editorial decision: {decision_type}")

    # -- SimContext interface --

    def make_tools(self) -> dict[str, Any]:
        return {
            "write_section": self.write_section,
            "revise_section": self.revise_section,
            "update_references": self.update_references,
            "review_sections": self.review_sections,
            "fact_check": self.fact_check,
            "peer_review": self.peer_review,
            "create_figure": self.create_figure,
            "insert_figure": self.insert_figure,
            "combine_sections": self.combine_sections,
            "make_editorial_decision": self.make_editorial_decision,
        }

    def is_complete(self) -> bool:
        # Revisions are conditional (only happen when review_sections fails),
        # so _revise_done is excluded from the completeness check — the same
        # design as ResearchSim.  Use _check_all_done() to honour _optional_items.
        return (self._check_all_done(self._write_done) and
                self._check_all_done(self._references_done) and
                self._check_all_done(self._review_done) and
                self._check_all_done(self._fact_check_done) and
                self._check_all_done(self._peer_review_done) and
                self._check_all_done(self._figure_done) and
                self._check_all_done(self._insert_figure_done) and
                self._check_all_done(self._combine_done) and
                self._check_all_done(self._editorial_done))

    @property
    def progress(self) -> dict[str, Any]:
        return {
            "writes": dict(self._write_done),
            "revisions": dict(self._revise_done),
            "references": dict(self._references_done),
            "reviews": dict(self._review_done),
            "fact_checks": dict(self._fact_check_done),
            "peer_reviews": dict(self._peer_review_done),
            "figures": dict(self._figure_done),
            "figure_insertions": dict(self._insert_figure_done),
            "combines": dict(self._combine_done),
            "editorial_decisions": dict(self._editorial_done),
            "all_complete": self.is_complete(),
        }
