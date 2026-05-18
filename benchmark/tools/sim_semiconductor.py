"""Parameterized semiconductor fab simulation shared by 4A+ tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._base import ToolResult
from .sim_base import SimContext


@dataclass
class StepperStep:
    """A stepper process step for one engineer."""

    engineer_id: str
    process: str


@dataclass
class DepositionStep:
    """A deposition process step for one engineer."""

    engineer_id: str
    process: str


@dataclass
class EtchStep:
    """An etch process step for one engineer."""

    engineer_id: str
    process: str


@dataclass
class MetrologyStep:
    """A metrology measurement step for one engineer."""

    engineer_id: str
    measurement: str


@dataclass
class MonitoringStep:
    """A monitoring check step for one engineer."""

    engineer_id: str
    check_type: str


class SemiconductorSim(SimContext):
    """Simulation for semiconductor fab pipelines with shared instruments.

    Tracks per-engineer progress through stepper, deposition, etch,
    metrology, and monitoring steps.  Detects violations such as
    missing instrument holds.

    Args:
        stepper_steps: Stepper process steps (each needs stepper).
        deposition_steps: Deposition steps (each needs dep_chamber).
        etch_steps: Etch process steps (each needs etch_chamber).
        metrology_steps: Metrology steps (each needs metrology_station).
        monitoring_steps: Monitoring steps (each needs monitor).
        instruments: List of shared instrument names (each modeled as a mutex).
    """

    # -- Decision tools (probabilistic failure for either/or branches) --

    _DECISION_TOOLS: dict[str, float] = {
        "run_metrology_measurement": 0.3,
        "run_etch_process": 0.3,
        "check_monitoring": 0.2,
    }

    # -- Resource requirements (for concurrent usage detection) --

    _TOOL_RESOURCES: dict[str, list[str]] = {
        "run_stepper_exposure": ["STEPPER"],
        "run_deposition": ["DEP_CHAMBER"],
        "run_etch_process": ["ETCH_CHAMBER"],
        "run_metrology_measurement": ["METROLOGY_STATION"],
        "check_monitoring": ["MONITOR"],
    }

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        return list(self._TOOL_RESOURCES.get(tool_name, []))

    # -- Simulated business-logic processing times --

    _TOOL_DELAYS: dict[str, tuple[float, float]] = {
        "run_stepper_exposure":       (0.5, 1.5),
        "run_deposition":             (0.5, 1.5),
        "run_etch_process":           (0.5, 1.5),
        "run_metrology_measurement":  (0.3, 1.0),
        "check_monitoring":           (0.2, 0.5),
    }

    def tool_delay(self, tool_name: str, **kwargs: Any) -> tuple[float, float]:
        return self._TOOL_DELAYS.get(tool_name, (0.0, 0.0))

    def __init__(
        self,
        stepper_steps: list[StepperStep],
        deposition_steps: list[DepositionStep],
        etch_steps: list[EtchStep],
        metrology_steps: list[MetrologyStep],
        monitoring_steps: list[MonitoringStep],
        instruments: list[str],
    ) -> None:
        super().__init__()

        self._instruments = list(instruments)

        # Build lookup dicts keyed by "engineer_process"
        self._stepper_steps = {f"{s.engineer_id}_{s.process}": s for s in stepper_steps}
        self._deposition_steps = {f"{s.engineer_id}_{s.process}": s for s in deposition_steps}
        self._etch_steps = {f"{s.engineer_id}_{s.process}": s for s in etch_steps}
        self._metrology_steps = {f"{s.engineer_id}_{s.measurement}": s for s in metrology_steps}
        self._monitoring_steps = {f"{s.engineer_id}_{s.check_type}": s for s in monitoring_steps}

        # Progress tracking
        self._stepper_done: dict[str, bool] = {k: False for k in self._stepper_steps}
        self._deposition_done: dict[str, bool] = {k: False for k in self._deposition_steps}
        self._etch_done: dict[str, bool] = {k: False for k in self._etch_steps}
        self._metrology_done: dict[str, bool] = {k: False for k in self._metrology_steps}
        self._monitoring_done: dict[str, bool] = {k: False for k in self._monitoring_steps}

        # Initialize instruments as resources
        for inst in instruments:
            self.init_resource(inst)

    # -- Tool implementations --

    def acquire_instrument(self, agent_id: str, instrument: str) -> ToolResult:
        """Attempt to exclusively acquire an instrument."""
        if not self.resource_exists(instrument):
            v = self.log_violation(
                agent_id, "acquire_instrument", "unknown_resource",
                f"Instrument '{instrument}' does not exist",
            )
            result = {"instrument": instrument, "status": "error", "reason": "unknown_resource"}
            self.log_event(agent_id, "acquire_instrument", {"instrument": instrument},
                           success=False, result=result, violations=[v])
            return ToolResult(tool_name="acquire_instrument", success=False,
                              data=result, message=f"Unknown instrument: {instrument}")

        acquired = self.try_acquire(instrument, agent_id)
        if acquired:
            result = {"instrument": instrument, "status": "acquired"}
            self.log_event(agent_id, "acquire_instrument", {"instrument": instrument},
                           success=True, result=result)
            return ToolResult(tool_name="acquire_instrument", success=True,
                              data=result, message=f"Acquired {instrument}")
        else:
            holder = self.holder_of(instrument)
            result = {"instrument": instrument, "status": "busy", "held_by": holder}
            self.log_event(agent_id, "acquire_instrument", {"instrument": instrument},
                           success=True, result=result)
            return ToolResult(tool_name="acquire_instrument", success=True,
                              data=result, message=f"{instrument} is busy (held by {holder})")

    def release_instrument(self, agent_id: str, instrument: str) -> ToolResult:
        """Release an instrument."""
        if not self.resource_exists(instrument):
            v = self.log_violation(
                agent_id, "release_instrument", "unknown_resource",
                f"Instrument '{instrument}' does not exist",
            )
            result = {"instrument": instrument, "status": "error", "reason": "unknown_resource"}
            self.log_event(agent_id, "release_instrument", {"instrument": instrument},
                           success=False, result=result, violations=[v])
            return ToolResult(tool_name="release_instrument", success=False,
                              data=result, message=f"Unknown instrument: {instrument}")

        released = self.release(instrument, agent_id)
        if released:
            result = {"instrument": instrument, "status": "released"}
            self.log_event(agent_id, "release_instrument", {"instrument": instrument},
                           success=True, result=result)
            return ToolResult(tool_name="release_instrument", success=True,
                              data=result, message=f"Released {instrument}")
        else:
            holder = self.holder_of(instrument)
            v = self.log_violation(
                agent_id, "release_instrument", "resource_not_held",
                f"{agent_id} cannot release '{instrument}' "
                f"(held by {holder or 'nobody'})",
            )
            result = {"instrument": instrument, "status": "error", "reason": "resource_not_held"}
            self.log_event(agent_id, "release_instrument", {"instrument": instrument},
                           success=False, result=result, violations=[v])
            return ToolResult(tool_name="release_instrument", success=False,
                              data=result, message=f"Cannot release {instrument}: not held by {agent_id}")

    def run_stepper_exposure(self, agent_id: str, process: str) -> ToolResult:
        """Run stepper process. Requires holding the stepper instrument."""
        self._mark_done(self._stepper_done, agent_id, process)

        result = {"process": process, "status": "stepper process complete", "engineer": agent_id}
        self.log_event(agent_id, "run_stepper_exposure", {"process": process},
                       success=True, result=result)
        return ToolResult(tool_name="run_stepper_exposure", success=True,
                          data=result, message=f"Stepper process complete: {process}")

    def run_deposition(self, agent_id: str, process: str) -> ToolResult:
        """Run deposition process. Requires holding the dep_chamber instrument."""
        self._mark_done(self._deposition_done, agent_id, process)

        result = {"process": process, "status": "deposition complete", "engineer": agent_id}
        self.log_event(agent_id, "run_deposition", {"process": process},
                       success=True, result=result)
        return ToolResult(tool_name="run_deposition", success=True,
                          data=result, message=f"Deposition complete: {process}")

    def run_etch_process(self, agent_id: str, process: str) -> ToolResult:
        """Run etch process. Requires holding the etch_chamber instrument."""
        if self.should_fail("run_etch_process", agent_id):
            result = {"process": process, "status": "etch_failed", "engineer": agent_id}
            self.log_event(agent_id, "run_etch_process", {"process": process},
                           success=False, result=result)
            return ToolResult(tool_name="run_etch_process", success=False,
                              data=result, message=f"Etch process failed: {process}")

        self._mark_done(self._etch_done, agent_id, process)
        result = {"process": process, "status": "etch process complete", "engineer": agent_id}
        self.log_event(agent_id, "run_etch_process", {"process": process},
                       success=True, result=result)
        return ToolResult(tool_name="run_etch_process", success=True,
                          data=result, message=f"Etch process complete: {process}")

    def run_metrology_measurement(self, agent_id: str, measurement: str) -> ToolResult:
        """Run metrology measurement. Requires holding the metrology_station."""
        if self.should_fail("run_metrology_measurement", agent_id):
            result = {"measurement": measurement, "status": "measurement_failed", "engineer": agent_id}
            self.log_event(agent_id, "run_metrology_measurement", {"measurement": measurement},
                           success=False, result=result)
            return ToolResult(tool_name="run_metrology_measurement", success=False,
                              data=result, message=f"Measurement failed: {measurement}")

        self._mark_done(self._metrology_done, agent_id, measurement)
        result = {"measurement": measurement, "status": "measurement complete", "engineer": agent_id}
        self.log_event(agent_id, "run_metrology_measurement", {"measurement": measurement},
                       success=True, result=result)
        return ToolResult(tool_name="run_metrology_measurement", success=True,
                          data=result, message=f"Measurement complete: {measurement}")

    def check_monitoring(self, agent_id: str, check_type: str) -> ToolResult:
        """Check process monitoring system. Requires holding the monitor."""
        if self.should_fail("check_monitoring", agent_id):
            result = {"check_type": check_type, "status": "check_failed", "engineer": agent_id}
            self.log_event(agent_id, "check_monitoring", {"check_type": check_type},
                           success=False, result=result)
            return ToolResult(tool_name="check_monitoring", success=False,
                              data=result, message=f"Monitoring check failed: {check_type}")

        self._mark_done(self._monitoring_done, agent_id, check_type)
        result = {"check_type": check_type, "status": "monitoring check complete", "engineer": agent_id}
        self.log_event(agent_id, "check_monitoring", {"check_type": check_type},
                       success=True, result=result)
        return ToolResult(tool_name="check_monitoring", success=True,
                          data=result, message=f"Monitoring check complete: {check_type}")

    # -- SimContext interface --

    def make_tools(self) -> dict[str, Any]:
        """Return tool dispatch dict for sim-mode registry."""
        return {
            "run_stepper_exposure": self.run_stepper_exposure,
            "run_deposition": self.run_deposition,
            "run_etch_process": self.run_etch_process,
            "run_metrology_measurement": self.run_metrology_measurement,
            "check_monitoring": self.check_monitoring,
        }

    def is_complete(self) -> bool:
        """All process steps must be completed (optional items skipped)."""
        return (self._check_all_done(self._stepper_done) and
                self._check_all_done(self._deposition_done) and
                self._check_all_done(self._etch_done) and
                self._check_all_done(self._metrology_done) and
                self._check_all_done(self._monitoring_done))

    @property
    def progress(self) -> dict[str, Any]:
        """Current progress toward the goal."""
        return {
            "stepper_processes": dict(self._stepper_done),
            "depositions": dict(self._deposition_done),
            "etch_processes": dict(self._etch_done),
            "metrology_measurements": dict(self._metrology_done),
            "monitoring_checks": dict(self._monitoring_done),
            "all_complete": self.is_complete(),
        }
