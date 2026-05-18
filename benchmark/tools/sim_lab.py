"""Parameterized laboratory simulation shared by 2A+ tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._base import ToolResult
from .sim_base import SimContext


@dataclass
class AnalysisStep:
    """A spectrometer analysis step for one scientist."""

    scientist_id: str
    sample: str


@dataclass
class SeparationStep:
    """A centrifuge separation step for one scientist."""

    scientist_id: str
    material: str


@dataclass
class TestStep:
    """A test step that requires no instrument."""

    scientist_id: str
    test_type: str


class LabSim(SimContext):
    """Simulation for lab experiments with shared instruments.

    Tracks per-scientist progress through analysis, separation,
    and testing steps.  Detects violations such as missing instrument
    holds and prerequisites.

    Args:
        analyses: Spectrometer analysis steps (each needs spectrometer).
        separations: Centrifuge separation steps (each needs centrifuge).
        tests: Test steps that need no instrument.
        instruments: List of shared instrument names (each modeled as a mutex).
    """

    def __init__(
        self,
        analyses: list[AnalysisStep],
        separations: list[SeparationStep],
        tests: list[TestStep],
        instruments: list[str],
    ) -> None:
        super().__init__()

        self._instruments = list(instruments)

        # Build lookup dicts keyed by "scientist_sample"
        self._analyses = {f"{a.scientist_id}_{a.sample}": a for a in analyses}
        self._separations = {f"{s.scientist_id}_{s.material}": s for s in separations}
        self._tests = {f"{t.scientist_id}_{t.test_type}": t for t in tests}

        # Progress tracking
        self._analysis_done: dict[str, bool] = {k: False for k in self._analyses}
        self._separation_done: dict[str, bool] = {k: False for k in self._separations}
        self._test_done: dict[str, bool] = {k: False for k in self._tests}

        # Initialize instruments as resources
        for inst in instruments:
            self.init_resource(inst)

    # -- Decision tools (probabilistic failure for either/or branches) --

    _DECISION_TOOLS: dict[str, float] = {
        "run_bioassay": 0.3,
    }

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

    def run_analysis(self, agent_id: str, sample: str) -> ToolResult:
        """Run spectrometer analysis on a sample."""
        self._mark_done(self._analysis_done, agent_id, sample)

        result = {"sample": sample, "status": "analysis complete", "scientist": agent_id}
        self.log_event(agent_id, "run_analysis", {"sample": sample},
                       success=True, result=result)
        return ToolResult(tool_name="run_analysis", success=True,
                          data=result, message=f"Analysis complete: {sample}")

    def run_separation(self, agent_id: str, material: str) -> ToolResult:
        """Run centrifuge separation on a material."""
        self._mark_done(self._separation_done, agent_id, material)

        result = {"material": material, "status": "separation complete", "scientist": agent_id}
        self.log_event(agent_id, "run_separation", {"material": material},
                       success=True, result=result)
        return ToolResult(tool_name="run_separation", success=True,
                          data=result, message=f"Separation complete: {material}")

    def run_bioassay(self, agent_id: str, compound: str, cell_type: str = "") -> ToolResult:
        """Run biological activity test. No instrument required."""
        if self.should_fail("run_bioassay", agent_id):
            result = {"compound": compound, "cell_type": cell_type,
                      "status": "bioassay_failed", "scientist": agent_id}
            self.log_event(agent_id, "run_bioassay",
                           {"compound": compound, "cell_type": cell_type},
                           success=False, result=result)
            return ToolResult(tool_name="run_bioassay", success=False,
                              data=result, message=f"Bioassay failed: {compound}")

        self._mark_done(self._test_done, agent_id, "bioassay")
        result = {"compound": compound, "cell_type": cell_type,
                  "status": "bioassay complete", "scientist": agent_id}
        self.log_event(agent_id, "run_bioassay",
                       {"compound": compound, "cell_type": cell_type},
                       success=True, result=result)
        return ToolResult(tool_name="run_bioassay", success=True,
                          data=result, message=f"Bioassay complete: {compound}")

    # -- SimContext interface --

    def make_tools(self) -> dict[str, Any]:
        """Return tool dispatch dict for sim-mode registry."""
        return {
            "run_analysis": self.run_analysis,
            "run_separation": self.run_separation,
            "run_bioassay": self.run_bioassay,
        }

    def is_complete(self) -> bool:
        """All analysis, separation, and test steps must be completed."""
        return (all(self._analysis_done.values()) and
                all(self._separation_done.values()) and
                all(self._test_done.values()))

    @property
    def progress(self) -> dict[str, Any]:
        """Current progress toward the goal."""
        return {
            "analyses": dict(self._analysis_done),
            "separations": dict(self._separation_done),
            "tests": dict(self._test_done),
            "all_complete": self.is_complete(),
        }
