"""Pharmaceutical Lab with Cascading QC and Safety simulation for task 13H.

Five scientists share SPECTROMETER + CENTRIFUGE + FUME_HOOD + CHROMATOGRAPH
plus a REAGENT_SUPPLY counter (initial=3).

Deadlock traps:
  1. Reverse lock ordering (CHEMIST: spec->cent, BIOLOGIST: cent->spec)
  2. QC hold-and-wait (FUME_HOOD + SPECTROMETER)
  3. SAFETY_OFFICER bulk acquire (all 4 instruments) -- deadlock risk if
     any scientist holds an instrument during safety inspection
  4. Cascading re-synthesis: QC_CONTROLLER rejects bio -> bio needs new
     compound -> CHEMIST re-synthesizes (costs reagent) -> counter
     exhaustion risk
  5. Circular feedback loop: CHEMIST->BIOLOGIST->ANALYST->QC_CONTROLLER->CHEMIST
"""

import json
from pathlib import Path
from typing import Any

from benchmark.tools._base import ToolResult
from benchmark.tools.sim_lab import (
    AnalysisStep, SeparationStep, TestStep, LabSim as _LabSim,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "13H" / "metadata.json").read_text()
)

_INSTRUMENTS = ["SPECTROMETER", "CENTRIFUGE", "FUME_HOOD", "CHROMATOGRAPH"]

_ANALYSES = [
    AnalysisStep(scientist_id="CHEMIST", sample="synthesized_compound"),
    AnalysisStep(scientist_id="CHEMIST", sample="final_validation"),
    AnalysisStep(scientist_id="BIOLOGIST", sample="fluorescence"),
    AnalysisStep(scientist_id="ANALYST", sample="molecular_detail"),
]

_SEPARATIONS = [
    SeparationStep(scientist_id="CHEMIST", material="compound_purification"),
    SeparationStep(scientist_id="BIOLOGIST", material="cell_cultures"),
    SeparationStep(scientist_id="ANALYST", material="verification"),
]

_TESTS: list[TestStep] = [
    TestStep(scientist_id="BIOLOGIST", test_type="bioassay"),
]


class PharmaLabCascadingSim(_LabSim):
    """13H: Pharma lab with cascading QC, SAFETY_OFFICER, and reagent counter."""

    _DECISION_TOOLS: dict[str, float] = {
        "run_synthesis": 0.3,
        "verify_result": 0.3,
    }

    def __init__(self) -> None:
        super().__init__(
            analyses=_ANALYSES,
            separations=_SEPARATIONS,
            tests=_TESTS,
            instruments=_INSTRUMENTS,
        )
        self.load_from_metadata(_METADATA)
        # REAGENT_SUPPLY counter: 3 units, each synthesis consumes one.
        # Modeled as a shared capacity resource so resource_requirements()
        # returns it and the monitor can track its use.
        self.init_resource("REAGENT_SUPPLY", capacity=3)
        self._reagent_units: int = 3  # remaining units (decremented on each synthesis)

        self._synthesis_done: dict[str, bool] = {"CHEMIST": False}
        self._chromatography_done: dict[str, bool] = {
            "ANALYST": False,
        }
        self._verification_done: dict[str, bool] = {
            "QC_CONTROLLER": False,
        }
        self._inspection_done: dict[str, bool] = {
            "SAFETY_OFFICER": False,
        }

    # -- Additional tool methods --

    def run_bioassay(self, agent_id: str, compound: str, cell_type: str = "") -> ToolResult:
        """Run biological activity test on the compound using cell cultures. No instrument required."""
        self._mark_done(self._test_done, agent_id, "bioassay")
        result = {"compound": compound, "cell_type": cell_type,
                  "status": "bioassay complete", "scientist": agent_id}
        self.log_event(agent_id, "run_bioassay",
                       {"compound": compound, "cell_type": cell_type},
                       success=True, result=result)
        return ToolResult(tool_name="run_bioassay", success=True,
                          data=result, message=f"Bioassay complete: {compound}")

    def run_synthesis(self, agent_id: str, compound: str) -> ToolResult:
        """Run chemical synthesis in the fume hood. Consumes one reagent unit. Can fail."""
        if self._reagent_units <= 0:
            result = {"compound": compound, "status": "reagent_exhausted",
                      "scientist": agent_id, "reagent_units_remaining": 0}
            self.log_event(agent_id, "run_synthesis", {"compound": compound},
                           success=False, result=result)
            return ToolResult(tool_name="run_synthesis", success=False,
                              data=result, message="Synthesis blocked: REAGENT_SUPPLY exhausted")

        if self.should_fail("run_synthesis", agent_id):
            # Reagent still consumed on a failed synthesis attempt
            self._reagent_units -= 1
            result = {"compound": compound, "status": "synthesis_failed",
                      "scientist": agent_id, "reagent_units_remaining": self._reagent_units}
            self.log_event(agent_id, "run_synthesis", {"compound": compound},
                           success=False, result=result)
            return ToolResult(tool_name="run_synthesis", success=False,
                              data=result, message=f"Synthesis failed: {compound}")

        self._reagent_units -= 1
        if agent_id in self._synthesis_done:
            self._synthesis_done[agent_id] = True
        result = {"compound": compound, "status": "synthesis complete",
                  "scientist": agent_id, "reagent_units_remaining": self._reagent_units}
        self.log_event(agent_id, "run_synthesis", {"compound": compound},
                       success=True, result=result)
        return ToolResult(tool_name="run_synthesis", success=True,
                          data=result, message=f"Synthesis complete: {compound}")

    def run_chromatography(self, agent_id: str, sample: str) -> ToolResult:
        """Run chromatographic separation and identification."""
        if agent_id in self._chromatography_done:
            self._chromatography_done[agent_id] = True
        result = {"sample": sample, "status": "chromatography complete",
                  "scientist": agent_id}
        self.log_event(agent_id, "run_chromatography", {"sample": sample},
                       success=True, result=result)
        return ToolResult(tool_name="run_chromatography", success=True,
                          data=result, message=f"Chromatography complete: {sample}")

    def verify_result(self, agent_id: str, scientist: str = "",
                      data_type: str = "") -> ToolResult:
        """Verify a scientist's result. Can reject, requiring the scientist to redo work."""
        if self.should_fail("verify_result", agent_id):
            result = {"scientist": scientist, "data_type": data_type,
                      "status": "rejected", "qc_agent": agent_id}
            self.log_event(agent_id, "verify_result",
                           {"scientist": scientist, "data_type": data_type},
                           success=False, result=result)
            return ToolResult(tool_name="verify_result", success=False,
                              data=result,
                              message=f"Rejected {scientist}'s {data_type} — redo required")

        if agent_id in self._verification_done:
            self._verification_done[agent_id] = True
        result = {"scientist": scientist, "data_type": data_type,
                  "status": "verified", "qc_agent": agent_id}
        self.log_event(agent_id, "verify_result",
                       {"scientist": scientist, "data_type": data_type},
                       success=True, result=result)
        return ToolResult(tool_name="verify_result", success=True,
                          data=result, message=f"Verified {scientist}'s {data_type}")

    def perform_inspection(self, agent_id: str, notes: str = "") -> ToolResult:
        """Perform a full safety inspection of all instruments. No additional instrument required."""
        if agent_id in self._inspection_done:
            self._inspection_done[agent_id] = True
        result = {"notes": notes, "status": "inspection complete", "inspector": agent_id}
        self.log_event(agent_id, "perform_inspection", {"notes": notes},
                       success=True, result=result)
        return ToolResult(tool_name="perform_inspection", success=True,
                          data=result, message=f"Safety inspection complete by {agent_id}")

    # -- Overrides --

    def make_tools(self) -> dict[str, Any]:
        return {
            "perform_inspection": self.perform_inspection,
            "run_analysis": self.run_analysis,
            "run_bioassay": self.run_bioassay,
            "run_separation": self.run_separation,
            "run_synthesis": self.run_synthesis,
            "run_chromatography": self.run_chromatography,
            "verify_result": self.verify_result,
        }

    def is_complete(self) -> bool:
        return (super().is_complete() and
                all(self._synthesis_done.values()) and
                all(self._chromatography_done.values()) and
                all(self._verification_done.values()) and
                all(self._inspection_done.values()))

    @property
    def progress(self) -> dict[str, Any]:
        base = super().progress
        base["syntheses"] = dict(self._synthesis_done)
        base["chromatography"] = dict(self._chromatography_done)
        base["verifications"] = dict(self._verification_done)
        base["inspections"] = dict(self._inspection_done)
        base["reagent_units_remaining"] = self._reagent_units
        base["all_complete"] = self.is_complete()
        return base
