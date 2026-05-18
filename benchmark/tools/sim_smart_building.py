"""Parameterized smart-building document simulation (scenarios 2E/2M/2H)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._base import ToolResult
from .sim_base import SimContext


@dataclass
class ReadStep:
    """A literature reading step."""

    agent_id: str
    topic: str


@dataclass
class DraftStep:
    """A section drafting step."""

    agent_id: str
    section: str


@dataclass
class WriteStep:
    """A document write step for one or more sections."""

    agent_id: str
    sections: list[str]


@dataclass
class ReviewStep:
    """A self-review step."""

    agent_id: str
    section: str


class SmartBuildingSim(SimContext):
    """Simulation for smart-building document collaboration.

    Tracks per-agent progress through read, draft, write, and review phases.
    Detects violations such as writing to the shared document without holding it.

    Args:
        read_steps: Literature reading steps (no resource required).
        draft_steps: Section drafting steps (no resource required).
        write_steps: Document write steps (need document).
        review_steps: Self-review steps (no resource required).
        resources: List of shared resource names.
    """

    def __init__(
        self,
        read_steps: list[ReadStep],
        draft_steps: list[DraftStep],
        write_steps: list[WriteStep],
        review_steps: list[ReviewStep],
        resources: list[str],
    ) -> None:
        super().__init__()

        self._read_steps = {f"{s.agent_id}_{s.topic}": s for s in read_steps}
        self._draft_steps = {f"{s.agent_id}_{s.section}": s for s in draft_steps}
        self._write_steps = {f"{s.agent_id}_{'_'.join(sorted(s.sections))}": s for s in write_steps}
        self._review_steps = {f"{s.agent_id}_{s.section}": s for s in review_steps}

        self._read_done: dict[str, bool] = {k: False for k in self._read_steps}
        self._draft_done: dict[str, bool] = {k: False for k in self._draft_steps}
        self._write_done: dict[str, bool] = {k: False for k in self._write_steps}
        self._review_done: dict[str, bool] = {k: False for k in self._review_steps}

        for res in resources:
            self.init_resource(res)

    # -- Decision tools (probabilistic failure for either/or branches) --

    _DECISION_TOOLS: dict[str, float] = {
        "review_own_work": 0.3,
    }

    # -- Simulated delays --

    _TOOL_DELAYS: dict[str, tuple[float, float]] = {
        "read_literature": (0.5, 1.5),
        "draft_content": (1.0, 2.0),
        "write_to_document": (0.5, 1.0),
        "review_own_work": (0.5, 1.5),
    }

    def tool_delay(self, tool_name: str, **kwargs: Any) -> tuple[float, float]:
        return self._TOOL_DELAYS.get(tool_name, (0.0, 0.0))

    # -- Tool implementations --

    def read_literature(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Read literature on a topic. No resource required."""
        topic = kwargs.get("topic", "unknown")

        key = self._match_key(self._read_done, agent_id, topic)
        if key in self._read_done:
            self._read_done[key] = True

        result = {"topic": topic, "status": "read", "agent": agent_id}
        self.log_event(agent_id, "read_literature", {"topic": topic},
                       success=True, result=result)
        return ToolResult(tool_name="read_literature", success=True,
                          data=result, message=f"Read literature on: {topic}")

    def draft_content(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Draft section content. No resource required."""
        section = self._get_param(kwargs, "section_name", "section")

        key = self._match_key(self._draft_done, agent_id, section)
        if key in self._draft_done:
            self._draft_done[key] = True

        result = {"section": section, "status": "drafted", "agent": agent_id}
        self.log_event(agent_id, "draft_content", {"section": section},
                       success=True, result=result)
        return ToolResult(tool_name="draft_content", success=True,
                          data=result, message=f"Drafted: {section}")

    def write_to_document(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Write sections to the shared document. Requires holding the corresponding section locks via acquire_lock."""
        sections = self._parse_list(kwargs.get("sections", []))
        sections_str = ", ".join(sections) if sections else "all"

        key = f"{agent_id}_{'_'.join(sorted(sections))}" if sections else f"{agent_id}_all"
        if key not in self._write_done:
            key = self._match_key(self._write_done, agent_id, "_".join(sorted(sections))) if sections else f"{agent_id}_all"
        if key in self._write_done:
            self._write_done[key] = True

        result = {"sections": sections, "status": "written", "agent": agent_id}
        self.log_event(agent_id, "write_to_document", {"sections": sections},
                       success=True, result=result)
        return ToolResult(tool_name="write_to_document", success=True,
                          data=result, message=f"Wrote to document: {sections_str}")

    def review_own_work(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Review own work on a section. No resource required."""
        section = self._get_param(kwargs, "section_name", "section")

        if self.should_fail("review_own_work", agent_id):
            result = {"section": section, "status": "needs_revision", "agent": agent_id}
            self.log_event(agent_id, "review_own_work", {"section": section},
                           success=False, result=result)
            return ToolResult(tool_name="review_own_work", success=False,
                              data=result, message=f"Review found issues: {section}")

        # Only mark done when review actually passes (agent may have no retry on failure)
        key = self._match_key(self._review_done, agent_id, section)
        if key in self._review_done:
            self._review_done[key] = True

        result = {"section": section, "status": "reviewed", "agent": agent_id}
        self.log_event(agent_id, "review_own_work", {"section": section},
                       success=True, result=result)
        return ToolResult(tool_name="review_own_work", success=True,
                          data=result, message=f"Reviewed: {section}")

    # -- SimContext interface --

    def make_tools(self) -> dict[str, Any]:
        return {
            "read_literature": self.read_literature,
            "draft_content": self.draft_content,
            "write_to_document": self.write_to_document,
            "review_own_work": self.review_own_work,
        }

    def is_complete(self) -> bool:
        return (all(self._read_done.values()) and
                all(self._draft_done.values()) and
                all(self._write_done.values()) and
                all(self._review_done.values()))

    @property
    def progress(self) -> dict[str, Any]:
        return {
            "reads": dict(self._read_done),
            "drafts": dict(self._draft_done),
            "writes": dict(self._write_done),
            "reviews": dict(self._review_done),
            "all_complete": self.is_complete(),
        }
