"""Parameterized pharmaceutical discovery simulation shared by 3A+ tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._base import ToolResult
from .sim_base import SimContext


@dataclass
class HplcStep:
    """An HPLC analysis step for one scientist."""

    scientist_id: str
    sample: str


@dataclass
class MassSpecStep:
    """A mass spectrometry analysis step for one scientist."""

    scientist_id: str
    sample: str


@dataclass
class CellAssayStep:
    """A cell-based assay step for one scientist."""

    scientist_id: str
    assay_type: str


class PharmaSim(SimContext):
    """Simulation for pharma discovery pipelines with shared instruments.

    Tracks per-scientist progress through HPLC analyses, mass spec analyses,
    and cell assays.  Detects violations such as missing instrument holds.

    Args:
        hplc_steps: HPLC analysis steps (each needs hplc).
        mass_spec_steps: Mass spec analysis steps (each needs mass_spec).
        cell_assay_steps: Cell assay steps (each needs cell_lab).
        instruments: List of shared instrument names (each modeled as a mutex).
    """

    def __init__(
        self,
        hplc_steps: list[HplcStep],
        mass_spec_steps: list[MassSpecStep],
        cell_assay_steps: list[CellAssayStep],
        instruments: list[str],
    ) -> None:
        super().__init__()

        self._instruments = list(instruments)

        # Build lookup dicts keyed by "scientist_sample"
        self._hplc_steps = {f"{s.scientist_id}_{s.sample}": s for s in hplc_steps}
        self._mass_spec_steps = {f"{s.scientist_id}_{s.sample}": s for s in mass_spec_steps}
        self._cell_assay_steps = {f"{s.scientist_id}_{s.assay_type}": s for s in cell_assay_steps}

        # Progress tracking
        self._hplc_done: dict[str, bool] = {k: False for k in self._hplc_steps}
        self._mass_spec_done: dict[str, bool] = {k: False for k in self._mass_spec_steps}
        self._cell_assay_done: dict[str, bool] = {k: False for k in self._cell_assay_steps}

        # Initialize instruments as resources
        for inst in instruments:
            self.init_resource(inst)

    # -- Decision tools (probabilistic failure for either/or branches) --

    _DECISION_TOOLS: dict[str, float] = {
        "run_hplc_analysis": 0.2,
        "run_mass_spec_analysis": 0.2,
        "run_cell_assay": 0.3,
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

    def run_hplc_analysis(self, agent_id: str, sample: str) -> ToolResult:
        """Run HPLC analysis. No resource required at this layer (instrument coordination handled by runtime)."""
        if self.should_fail("run_hplc_analysis", agent_id):
            result = {"sample": sample, "status": "hplc_failed", "scientist": agent_id}
            self.log_event(agent_id, "run_hplc_analysis", {"sample": sample},
                           success=False, result=result)
            return ToolResult(tool_name="run_hplc_analysis", success=False,
                              data=result, message=f"HPLC analysis failed: {sample}")

        self._mark_done(self._hplc_done, agent_id, sample)
        result = {"sample": sample, "status": "hplc analysis complete", "scientist": agent_id}
        self.log_event(agent_id, "run_hplc_analysis", {"sample": sample},
                       success=True, result=result)
        return ToolResult(tool_name="run_hplc_analysis", success=True,
                          data=result, message=f"HPLC analysis complete: {sample}")

    def run_mass_spec_analysis(self, agent_id: str, sample: str) -> ToolResult:
        """Run mass spec analysis. No resource required at this layer (instrument coordination handled by runtime)."""
        if self.should_fail("run_mass_spec_analysis", agent_id):
            result = {"sample": sample, "status": "mass_spec_failed", "scientist": agent_id}
            self.log_event(agent_id, "run_mass_spec_analysis", {"sample": sample},
                           success=False, result=result)
            return ToolResult(tool_name="run_mass_spec_analysis", success=False,
                              data=result, message=f"Mass spec analysis failed: {sample}")

        self._mark_done(self._mass_spec_done, agent_id, sample)
        result = {"sample": sample, "status": "mass spec analysis complete", "scientist": agent_id}
        self.log_event(agent_id, "run_mass_spec_analysis", {"sample": sample},
                       success=True, result=result)
        return ToolResult(tool_name="run_mass_spec_analysis", success=True,
                          data=result, message=f"Mass spec analysis complete: {sample}")

    def run_cell_assay(self, agent_id: str, assay_type: str) -> ToolResult:
        """Run cell-based assay. No resource required at this layer (instrument coordination handled by runtime)."""
        if self.should_fail("run_cell_assay", agent_id):
            result = {"assay_type": assay_type, "status": "assay_failed", "scientist": agent_id}
            self.log_event(agent_id, "run_cell_assay", {"assay_type": assay_type},
                           success=False, result=result)
            return ToolResult(tool_name="run_cell_assay", success=False,
                              data=result, message=f"Cell assay failed: {assay_type}")

        self._mark_done(self._cell_assay_done, agent_id, assay_type)
        result = {"assay_type": assay_type, "status": "cell assay complete", "scientist": agent_id}
        self.log_event(agent_id, "run_cell_assay", {"assay_type": assay_type},
                       success=True, result=result)
        return ToolResult(tool_name="run_cell_assay", success=True,
                          data=result, message=f"Cell assay complete: {assay_type}")

    # -- SimContext interface --

    def make_tools(self) -> dict[str, Any]:
        """Return tool dispatch dict for sim-mode registry."""
        return {
            "run_hplc_analysis": self.run_hplc_analysis,
            "run_mass_spec_analysis": self.run_mass_spec_analysis,
            "run_cell_assay": self.run_cell_assay,
        }

    def is_complete(self) -> bool:
        """All HPLC, mass spec, and cell assay steps must be completed."""
        return (all(self._hplc_done.values()) and
                all(self._mass_spec_done.values()) and
                all(self._cell_assay_done.values()))

    @property
    def progress(self) -> dict[str, Any]:
        """Current progress toward the goal."""
        return {
            "hplc_analyses": dict(self._hplc_done),
            "mass_spec_analyses": dict(self._mass_spec_done),
            "cell_assays": dict(self._cell_assay_done),
            "all_complete": self.is_complete(),
        }
