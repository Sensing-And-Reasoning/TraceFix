"""Parameterized research writing simulation (scenarios 3E/3M/3H)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._base import ToolResult
from .sim_base import SimContext


@dataclass
class ResearchStep:
    """A topic research step."""

    agent_id: str
    topic: str


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
    scope: str  # e.g. "all", "section_intro"


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


class ResearchSim(SimContext):
    """Simulation for collaborative research writing.

    Tracks per-agent progress through research, writing, revision, review,
    and editorial phases.  Detects resource-hold violations for document
    and bibliography access.

    Args:
        research_steps: Topic research steps.
        write_steps: Section writing steps (need document).
        revise_steps: Section revision steps (need document).
        references_steps: Reference update steps (need bibliography).
        review_steps: Review steps.
        fact_check_steps: Fact-checking steps.
        peer_review_steps: Peer review steps.
        figure_steps: Figure creation steps.
        insert_figure_steps: Figure insertion steps (need document).
        combine_steps: Sections combination steps (need document).
        editorial_steps: Editorial decision steps.
        resources: List of shared resource names.
    """

    def __init__(
        self,
        research_steps: list[ResearchStep] | None = None,
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

        self._research_steps = {f"{s.agent_id}_{s.topic}": s for s in (research_steps or [])}
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

        self._research_done: dict[str, bool] = {k: False for k in self._research_steps}
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

    # Maps section names to their exclusive draft locks (used by 3H per-section model).
    _SECTION_LOCK_MAP: dict[str, str] = {
        "section_a": "SECTION_A",
        "section_b": "SECTION_B",
        "section_c": "SECTION_C",
        "section_d": "SECTION_D",
    }

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        """Return resources needed by *tool_name*.

        Delegates to the metadata-driven mapping loaded from metadata.json
        (``tool_resource_map`` / ``agent_resources``).  Handles the special
        case of ``insert_figure``, whose required section lock is resolved
        dynamically from the ``section_name`` argument.
        """
        base = super().resource_requirements(tool_name, **kwargs)
        if base:
            return base
        # Dynamic: insert_figure acquires the draft lock for its target section.
        if tool_name == "insert_figure":
            section = kwargs.get("section_name") or kwargs.get("section", "")
            lock = self._SECTION_LOCK_MAP.get(section.lower().strip(), "")
            if lock and self.resource_exists(lock):
                return [lock]
        return []

    # -- Simulated delays --

    _TOOL_DELAYS: dict[str, tuple[float, float]] = {
        "research_topic": (1.0, 3.0),
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

    def research_topic(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Research a topic. No resource required."""
        topic = kwargs.get("topic", "unknown")

        key = self._match_key(self._research_done, agent_id, topic)
        if key in self._research_done:
            self._research_done[key] = True

        result = {"topic": topic, "status": "researched", "agent": agent_id}
        self.log_event(agent_id, "research_topic", {"topic": topic},
                       success=True, result=result)
        return ToolResult(tool_name="research_topic", success=True,
                          data=result, message=f"Researched: {topic}")

    def write_section(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Write a section. Requires holding the section draft lock."""
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
        """Revise a section. Requires holding the section draft lock."""
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
        """Update references. Requires holding the DATABASE lock."""
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
        section = self._get_param(kwargs, "section_name", "section")

        key = self._match_key(self._fact_check_done, agent_id, section)

        if self.should_fail("fact_check", agent_id):
            result = {"section": section, "status": "issues_found", "agent": agent_id}
            self.log_event(agent_id, "fact_check", {"section": section},
                           success=False, result=result)
            return ToolResult(tool_name="fact_check", success=False,
                              data=result, message=f"Fact check found issues: {section}")

        if key in self._fact_check_done:
            self._fact_check_done[key] = True

        result = {"section": section, "status": "fact checked", "agent": agent_id}
        self.log_event(agent_id, "fact_check", {"section": section},
                       success=True, result=result)
        return ToolResult(tool_name="fact_check", success=True,
                          data=result, message=f"Fact checked: {section}")

    def peer_review(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Peer review a section. No resource required."""
        section = self._get_param(kwargs, "section_name", "section", "manuscript")

        key = self._match_key(self._peer_review_done, agent_id, section)

        if self.should_fail("peer_review", agent_id):
            result = {"section": section, "status": "revision_requested", "agent": agent_id}
            self.log_event(agent_id, "peer_review", {"section": section},
                           success=False, result=result)
            return ToolResult(tool_name="peer_review", success=False,
                              data=result, message=f"Peer review requests revision: {section}")

        if key in self._peer_review_done:
            self._peer_review_done[key] = True

        result = {"section": section, "status": "peer reviewed", "agent": agent_id}
        self.log_event(agent_id, "peer_review", {"section": section},
                       success=True, result=result)
        return ToolResult(tool_name="peer_review", success=True,
                          data=result, message=f"Peer reviewed: {section}")

    def _extract_figure_id(self, kwargs: dict[str, Any]) -> str:
        """Extract figure ID from tool call arguments.

        Handles both explicit ``figure_id`` and free-text ``description``
        (e.g. "figures for section D" → "fig_d").
        """
        # Try explicit figure_id / figure params first
        for name in ("figure_id", "figure"):
            val = kwargs.get(name)
            if val is not None:
                return val

        # Fall back: extract section reference from description
        desc = kwargs.get("description", "")
        if desc:
            norm = self._normalize(desc)
            # Look for "section_X" pattern and derive "fig_X"
            import re
            m = re.search(r"section[_\s]*([a-z])", norm)
            if m:
                return f"fig_{m.group(1)}"
        return "unknown"

    def create_figure(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Create a figure. Requires holding the FIGURE_REPOSITORY lock."""
        figure_id = self._extract_figure_id(kwargs)

        key = self._match_key(self._figure_done, agent_id, figure_id)
        if key in self._figure_done:
            self._figure_done[key] = True

        result = {"figure_id": figure_id, "status": "created", "agent": agent_id}
        self.log_event(agent_id, "create_figure", {"figure_id": figure_id},
                       success=True, result=result)
        return ToolResult(tool_name="create_figure", success=True,
                          data=result, message=f"Created figure: {figure_id}")

    def insert_figure(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Insert a figure into a section. Requires holding the section draft lock."""
        figure_id = self._get_param(kwargs, "figure_id", "figure")
        section = self._get_param(kwargs, "section_name", "section")

        key = self._match_key(self._insert_figure_done, agent_id, figure_id)
        if key in self._insert_figure_done:
            self._insert_figure_done[key] = True

        result = {"figure_id": figure_id, "section": section, "status": "inserted", "agent": agent_id}
        self.log_event(agent_id, "insert_figure", {"figure_id": figure_id, "section": section},
                       success=True, result=result)
        return ToolResult(tool_name="insert_figure", success=True,
                          data=result, message=f"Inserted figure {figure_id} into {section}")

    def combine_sections(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Combine sections into final document. Requires holding the DOCUMENT lock (3E/3M)."""
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
        decision_type = self._get_param(kwargs, "decision_type", "decision")

        # If decision_type wasn't found via explicit params, try to match
        # against unmatched editorial keys for this agent.
        # This handles free-text params like review_summary where the value
        # doesn't correspond to a decision_type keyword.
        key = self._match_key(self._editorial_done, agent_id, decision_type)
        if key not in self._editorial_done:
            # Fall back: find first incomplete non-optional editorial step,
            # then fall back to optional ones.
            prefix = f"{agent_id}_"
            candidates = [k for k, done in self._editorial_done.items()
                          if k.startswith(prefix) and not done]
            required = [k for k in candidates if k not in self._optional_items]
            key = (required or candidates or [key])[0]

        if self.should_fail("make_editorial_decision", agent_id):
            result = {"decision_type": decision_type, "status": "rejected", "agent": agent_id}
            self.log_event(agent_id, "make_editorial_decision", {"decision_type": decision_type},
                           success=False, result=result)
            return ToolResult(tool_name="make_editorial_decision", success=False,
                              data=result, message=f"Editorial decision rejected: {decision_type}")

        if key in self._editorial_done:
            self._editorial_done[key] = True

        result = {"decision_type": decision_type, "status": "decided", "agent": agent_id}
        self.log_event(agent_id, "make_editorial_decision", {"decision_type": decision_type},
                       success=True, result=result)
        return ToolResult(tool_name="make_editorial_decision", success=True,
                          data=result, message=f"Editorial decision: {decision_type}")

    # -- SimContext interface --

    def make_tools(self) -> dict[str, Any]:
        return {
            "research_topic": self.research_topic,
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
        # Revisions are always conditional (only happen when reviewer
        # rejects), so they are excluded from the completeness check.
        return (self._check_all_done(self._research_done) and
                self._check_all_done(self._write_done) and
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
            "research": dict(self._research_done),
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
