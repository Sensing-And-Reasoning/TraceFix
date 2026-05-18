"""Parameterized flexible manufacturing simulation (scenarios 11E/11M/11H)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._base import ToolResult
from .sim_base import SimContext


@dataclass
class JobStep:
    """An assembly job step."""

    agent_id: str
    job_id: str


@dataclass
class InspectStep:
    """A quality inspection step."""

    agent_id: str
    job_id: str


@dataclass
class ReplenishStep:
    """A material replenishment step."""

    agent_id: str
    material: str


@dataclass
class PackageStep:
    """A packaging step."""

    agent_id: str
    job_id: str


@dataclass
class CollectReportsStep:
    """A report collection step."""

    agent_id: str
    scope: str


@dataclass
class ReworkStep:
    """A rework dispatch step."""

    agent_id: str
    job_id: str


class ManufacturingSim(SimContext):
    """Simulation for flexible manufacturing.

    Tracks per-agent progress through assembly, inspection, material
    management, packaging, reporting, and rework phases.  Subclasses
    override ``_TOOL_RESOURCES`` to declare which domain resources (if any)
    are required by each tool.  All resource requirements default to empty
    (no sim-level resource checks) so that coordination enforcement is handled
    entirely by the runtime protocol layer.

    Args:
        job_steps: Assembly job steps.
        inspect_steps: Quality inspection steps.
        replenish_steps: Material replenishment steps.
        package_steps: Packaging steps.
        collect_reports_steps: Report collection steps.
        rework_steps: Rework dispatch steps.
        resources: List of shared resource names to initialize in the sim.
    """

    def __init__(
        self,
        job_steps: list[JobStep] | None = None,
        inspect_steps: list[InspectStep] | None = None,
        replenish_steps: list[ReplenishStep] | None = None,
        package_steps: list[PackageStep] | None = None,
        collect_reports_steps: list[CollectReportsStep] | None = None,
        rework_steps: list[ReworkStep] | None = None,
        resources: list[str] | None = None,
    ) -> None:
        super().__init__()

        self._job_steps = {f"{s.agent_id}_{s.job_id}": s for s in (job_steps or [])}
        self._inspect_steps = {f"{s.agent_id}_{s.job_id}": s for s in (inspect_steps or [])}
        self._replenish_steps = {f"{s.agent_id}_{s.material}": s for s in (replenish_steps or [])}
        self._package_steps = {f"{s.agent_id}_{s.job_id}": s for s in (package_steps or [])}
        self._collect_reports_steps = {f"{s.agent_id}_{s.scope}": s for s in (collect_reports_steps or [])}
        self._rework_steps = {f"{s.agent_id}_{s.job_id}": s for s in (rework_steps or [])}

        self._job_done: dict[str, bool] = {k: False for k in self._job_steps}
        self._inspect_done: dict[str, bool] = {k: False for k in self._inspect_steps}
        self._replenish_done: dict[str, bool] = {k: False for k in self._replenish_steps}
        self._package_done: dict[str, bool] = {k: False for k in self._package_steps}
        self._collect_reports_done: dict[str, bool] = {k: False for k in self._collect_reports_steps}
        self._rework_done: dict[str, bool] = {k: False for k in self._rework_steps}

        for res in (resources or []):
            self.init_resource(res)

    # -- Decision tools (probabilistic failure for either/or branches) --

    _DECISION_TOOLS: dict[str, float] = {
        "inspect_quality": 0.3,
    }

    # -- Resource requirements --
    # Subclasses override this to declare which resources (if any) each tool
    # requires.  The base class default is empty (no sim-level resource checks)
    # so that coordination enforcement is handled by the runtime protocol layer.

    _TOOL_RESOURCES: dict[str, list[str]] = {
        "do_job": [],
        "inspect_quality": [],
        "replenish_material": [],
        "package_goods": [],
        "collect_reports": [],
        "dispatch_rework": [],
    }

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        # If metadata was loaded via load_from_metadata(), delegate to SimContext
        # logic which supports "@agent_resources" and static list specs.
        if self._tool_resource_map:
            return super().resource_requirements(tool_name, **kwargs)
        # Fall back to class-level _TOOL_RESOURCES override.
        return list(self._TOOL_RESOURCES.get(tool_name, []))

    # -- Simulated delays --

    _TOOL_DELAYS: dict[str, tuple[float, float]] = {
        "do_job": (2.0, 5.0),
        "inspect_quality": (1.0, 3.0),
        "replenish_material": (0.5, 1.5),
        "package_goods": (1.0, 2.0),
        "collect_reports": (0.5, 1.0),
        "dispatch_rework": (1.0, 3.0),
    }

    def tool_delay(self, tool_name: str, **kwargs: Any) -> tuple[float, float]:
        return self._TOOL_DELAYS.get(tool_name, (0.0, 0.0))

    # -- Tool implementations --

    def do_job(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Execute an assembly job. No resource required (subclasses override _TOOL_RESOURCES)."""
        job_id = kwargs.get("job_id", "unknown")

        self._mark_done(self._job_done, agent_id, job_id)

        result = {"job_id": job_id, "status": "completed", "agent": agent_id}
        self.log_event(agent_id, "do_job", {"job_id": job_id},
                       success=True, result=result)
        return ToolResult(tool_name="do_job", success=True,
                          data=result, message=f"Job completed: {job_id}")

    def inspect_quality(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Inspect quality. No resource required (subclasses override _TOOL_RESOURCES)."""
        job_id = kwargs.get("job_id", "unknown")

        if self.should_fail("inspect_quality", agent_id):
            result = {"job_id": job_id, "status": "failed_inspection", "agent": agent_id}
            self.log_event(agent_id, "inspect_quality", {"job_id": job_id},
                           success=False, result=result)
            return ToolResult(tool_name="inspect_quality", success=False,
                              data=result, message=f"Quality inspection FAILED: {job_id}")

        self._mark_done(self._inspect_done, agent_id, job_id)

        result = {"job_id": job_id, "status": "inspected", "agent": agent_id}
        self.log_event(agent_id, "inspect_quality", {"job_id": job_id},
                       success=True, result=result)
        return ToolResult(tool_name="inspect_quality", success=True,
                          data=result, message=f"Quality inspected: {job_id}")

    def replenish_material(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Replenish material. No resource required (subclasses override _TOOL_RESOURCES)."""
        material = kwargs.get("material", "unknown")

        self._mark_done(self._replenish_done, agent_id, material)

        result = {"material": material, "status": "replenished", "agent": agent_id}
        self.log_event(agent_id, "replenish_material", {"material": material},
                       success=True, result=result)
        return ToolResult(tool_name="replenish_material", success=True,
                          data=result, message=f"Material replenished: {material}")

    def package_goods(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Package goods. No resource required (subclasses override _TOOL_RESOURCES)."""
        job_id = kwargs.get("batch_id", kwargs.get("job_id", "unknown"))

        self._mark_done(self._package_done, agent_id, job_id)

        result = {"job_id": job_id, "status": "packaged", "agent": agent_id}
        self.log_event(agent_id, "package_goods", {"job_id": job_id},
                       success=True, result=result)
        return ToolResult(tool_name="package_goods", success=True,
                          data=result, message=f"Goods packaged: {job_id}")

    def collect_reports(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Collect reports. No resource required."""
        scope = kwargs.get("scope", "all")

        self._mark_done(self._collect_reports_done, agent_id, scope)

        result = {"scope": scope, "status": "collected", "agent": agent_id}
        self.log_event(agent_id, "collect_reports", {"scope": scope},
                       success=True, result=result)
        return ToolResult(tool_name="collect_reports", success=True,
                          data=result, message=f"Reports collected: {scope}")

    def dispatch_rework(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Dispatch rework. No resource required (subclasses override _TOOL_RESOURCES)."""
        job_id = kwargs.get("job_id", "unknown")

        self._mark_done(self._rework_done, agent_id, job_id)

        result = {"job_id": job_id, "status": "rework dispatched", "agent": agent_id}
        self.log_event(agent_id, "dispatch_rework", {"job_id": job_id},
                       success=True, result=result)
        return ToolResult(tool_name="dispatch_rework", success=True,
                          data=result, message=f"Rework dispatched: {job_id}")

    # -- SimContext interface --

    def make_tools(self) -> dict[str, Any]:
        return {
            "do_job": self.do_job,
            "inspect_quality": self.inspect_quality,
            "replenish_material": self.replenish_material,
            "package_goods": self.package_goods,
            "collect_reports": self.collect_reports,
            "dispatch_rework": self.dispatch_rework,
        }

    def is_complete(self) -> bool:
        return (all(self._job_done.values()) and
                all(self._inspect_done.values()) and
                all(self._replenish_done.values()) and
                all(self._package_done.values()) and
                all(self._collect_reports_done.values()) and
                all(self._rework_done.values()))

    @property
    def progress(self) -> dict[str, Any]:
        return {
            "jobs": dict(self._job_done),
            "inspections": dict(self._inspect_done),
            "replenishments": dict(self._replenish_done),
            "packages": dict(self._package_done),
            "reports": dict(self._collect_reports_done),
            "reworks": dict(self._rework_done),
            "all_complete": self.is_complete(),
        }
