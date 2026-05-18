"""Drug Discovery Pipeline with Regulatory Review simulation for task 14M.

Five scientists share hplc + mass_spec + cell_lab.  Adds:
  1. Regulatory review gate after lead's decision (approve/reject)
  2. Assay failures (cell_assay and hplc can fail)
  3. Regulatory rejection loops back to lead, who may re-request assays
"""

from typing import Any

from benchmark.tools._base import ToolResult
from benchmark.tools.sim_pharma import (
    HplcStep, MassSpecStep, CellAssayStep, PharmaSim as _PharmaSim,
)

_INSTRUMENTS = ["HPLC", "MASS_SPEC", "CELL_LAB"]

_HPLC_STEPS = [
    HplcStep(scientist_id="CHEMIST", sample="synthesis_qc"),
    HplcStep(scientist_id="CHEMIST", sample="documentation"),
    HplcStep(scientist_id="BIOLOGIST", sample="stability"),
    HplcStep(scientist_id="TOXICOLOGIST", sample="purity_check"),
    HplcStep(scientist_id="LEAD_SCIENTIST", sample="structural_confirmation"),
]

_MASS_SPEC_STEPS = [
    MassSpecStep(scientist_id="CHEMIST", sample="molecular_id"),
    MassSpecStep(scientist_id="TOXICOLOGIST", sample="baseline_markers"),
    MassSpecStep(scientist_id="LEAD_SCIENTIST", sample="reference_methods"),
    MassSpecStep(scientist_id="LEAD_SCIENTIST", sample="characterization"),
]

_CELL_ASSAY_STEPS = [
    CellAssayStep(scientist_id="BIOLOGIST", assay_type="culture_prep"),
    CellAssayStep(scientist_id="BIOLOGIST", assay_type="bioassay"),
    CellAssayStep(scientist_id="TOXICOLOGIST", assay_type="cytotoxicity"),
]


_METADATA = {
    "agents": ["BIOLOGIST", "CHEMIST", "LEAD_SCIENTIST", "REGULATORY_SPECIALIST", "TOXICOLOGIST"],
    "resources": ["CELL_LAB", "HPLC", "MASS_SPEC"],
    "agent_resources": {
        "BIOLOGIST": ["CELL_LAB", "HPLC"],
        "CHEMIST": ["HPLC", "MASS_SPEC"],
        "LEAD_SCIENTIST": ["HPLC", "MASS_SPEC"],
        "REGULATORY_SPECIALIST": [],
        "TOXICOLOGIST": ["CELL_LAB", "HPLC", "MASS_SPEC"],
    },
    "tool_resource_map": {
        "run_hplc_analysis": ["HPLC"],
        "run_mass_spec_analysis": ["MASS_SPEC"],
        "run_cell_assay": ["CELL_LAB"],
        "verify_regulatory_compliance": [],
    },
}


class DrugDiscoveryRegulatorySim(_PharmaSim):
    """14M: Drug discovery with regulatory review gate and assay failures.

    run_mass_spec_analysis is non-failing (can_fail=false); excluded from
    _DECISION_TOOLS to prevent spurious failure injection.
    """

    _DECISION_TOOLS: dict[str, float] = {
        "run_hplc_analysis": 0.2,
        "run_cell_assay": 0.3,
        "verify_regulatory_compliance": 0.2,
    }

    def __init__(self) -> None:
        super().__init__(
            hplc_steps=_HPLC_STEPS,
            mass_spec_steps=_MASS_SPEC_STEPS,
            cell_assay_steps=_CELL_ASSAY_STEPS,
            instruments=_INSTRUMENTS,
        )
        self._regulatory_done: dict[str, bool] = {
            "REGULATORY_SPECIALIST_compliance": False,
        }
        self.load_from_metadata(_METADATA)

    # -- Additional tool methods --

    def verify_regulatory_compliance(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Verify regulatory compliance. Can reject."""
        if self.should_fail("verify_regulatory_compliance", agent_id):
            result = {"status": "rejected", "agent": agent_id, **kwargs}
            self.log_event(agent_id, "verify_regulatory_compliance", kwargs,
                           success=False, result=result)
            return ToolResult(tool_name="verify_regulatory_compliance", success=False,
                              data=result, message="Regulatory compliance rejected")

        self._mark_done(self._regulatory_done, agent_id, "compliance")
        result = {"status": "approved", "agent": agent_id, **kwargs}
        self.log_event(agent_id, "verify_regulatory_compliance", kwargs,
                       success=True, result=result)
        return ToolResult(tool_name="verify_regulatory_compliance", success=True,
                          data=result, message="Regulatory compliance approved")

    # -- Overrides --

    def make_tools(self) -> dict[str, Any]:
        tools = super().make_tools()
        tools["verify_regulatory_compliance"] = self.verify_regulatory_compliance
        return tools

    def is_complete(self) -> bool:
        return (super().is_complete() and
                all(self._regulatory_done.values()))

    @property
    def progress(self) -> dict[str, Any]:
        base = super().progress
        base["regulatory"] = dict(self._regulatory_done)
        base["all_complete"] = self.is_complete()
        return base
