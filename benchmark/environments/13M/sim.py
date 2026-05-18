"""Pharmaceutical Lab with QC Review simulation config for task 13M.

Four scientists share SPECTROMETER + CENTRIFUGE + FUME_HOOD.  Contains:
  1. Reverse lock ordering (CHEMIST: spec->cent, BIOLOGIST: cent->spec)
  2. QC hold-and-wait (QC_CONTROLLER needs FUME_HOOD + SPECTROMETER for verification)
  3. QC rejection loops force retry cycles
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
     / "descriptions" / "13M" / "metadata.json").read_text()
)

_INSTRUMENTS = ["SPECTROMETER", "CENTRIFUGE", "FUME_HOOD"]

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


class PharmaLabQCSim(_LabSim):
    """13M: Pharmaceutical lab with QC rejection loops and 3-instrument contention."""

    _DECISION_TOOLS: dict[str, float] = {
        "run_bioassay": 0.3,
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
        self._synthesis_done: dict[str, bool] = {"CHEMIST": False}
        self._verification_done: dict[str, bool] = {
            "QC_CONTROLLER_purification": False,
            "QC_CONTROLLER_bioassay": False,
        }

    # -- Additional tool methods --

    def run_bioassay(self, agent_id: str, compound: str, cell_type: str = "") -> ToolResult:
        """Run biological activity test on the compound using cell cultures. No instrument required."""
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

    def run_synthesis(self, agent_id: str, compound: str) -> ToolResult:
        """Run chemical synthesis in the fume hood. No failure injection (synthesis is done once)."""
        if agent_id in self._synthesis_done:
            self._synthesis_done[agent_id] = True
        result = {"compound": compound, "status": "synthesis complete",
                  "scientist": agent_id}
        self.log_event(agent_id, "run_synthesis", {"compound": compound},
                       success=True, result=result)
        return ToolResult(tool_name="run_synthesis", success=True,
                          data=result, message=f"Synthesis complete: {compound}")

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

        key = f"{agent_id}_{data_type}"
        if key in self._verification_done:
            self._verification_done[key] = True
        result = {"scientist": scientist, "data_type": data_type,
                  "status": "verified", "qc_agent": agent_id}
        self.log_event(agent_id, "verify_result",
                       {"scientist": scientist, "data_type": data_type},
                       success=True, result=result)
        return ToolResult(tool_name="verify_result", success=True,
                          data=result, message=f"Verified {scientist}'s {data_type}")

    # -- Overrides --

    def make_tools(self) -> dict[str, Any]:
        return {
            "run_analysis": self.run_analysis,
            "run_bioassay": self.run_bioassay,
            "run_separation": self.run_separation,
            "run_synthesis": self.run_synthesis,
            "verify_result": self.verify_result,
        }

    def is_complete(self) -> bool:
        return (super().is_complete() and
                all(self._synthesis_done.values()) and
                all(self._verification_done.values()))

    @property
    def progress(self) -> dict[str, Any]:
        base = super().progress
        base["syntheses"] = dict(self._synthesis_done)
        base["verifications"] = dict(self._verification_done)
        base["all_complete"] = self.is_complete()
        return base
