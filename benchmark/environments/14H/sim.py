"""Drug Discovery Pipeline with Multi-Round Trials simulation for task 14H.

Seven scientists share hplc + mass_spec + cell_lab + formulation_suite
plus a biological_samples counter (initial=3).

Deadlock traps:
  1. 4-instrument contention with 7 agents
  2. Counter limits total bio/tox attempts (biological_samples=3)
  3. Circular dependency: PROJECT_DIRECTOR->CHEMIST->FORMULATION_SCIENTIST->bio/tox->CLINICAL_LEAD->REGULATORY_SPECIALIST->PROJECT_DIRECTOR
  4. Regulatory hold blocks CLINICAL_LEAD + PROJECT_DIRECTOR (acquires hplc+mass_spec)
  5. Parallel bio+tox fan-in with nondeterministic order
  6. Cascading re-synthesis: tox failure -> new formulation -> new synthesis
"""

from typing import Any

from benchmark.tools._base import ToolResult
from benchmark.tools.sim_pharma import (
    HplcStep, MassSpecStep, CellAssayStep, PharmaSim as _PharmaSim,
)

_INSTRUMENTS = ["HPLC", "MASS_SPEC", "CELL_LAB", "FORMULATION_SUITE"]

_HPLC_STEPS = [
    HplcStep(scientist_id="CHEMIST", sample="synthesis_qc"),
    HplcStep(scientist_id="CHEMIST", sample="documentation"),
    HplcStep(scientist_id="BIOLOGIST", sample="stability"),
    HplcStep(scientist_id="TOXICOLOGIST", sample="purity_check"),
]

_MASS_SPEC_STEPS = [
    MassSpecStep(scientist_id="CHEMIST", sample="molecular_id"),
    MassSpecStep(scientist_id="TOXICOLOGIST", sample="baseline_markers"),
    MassSpecStep(scientist_id="CLINICAL_LEAD", sample="combined_review"),
]

_CELL_ASSAY_STEPS = [
    CellAssayStep(scientist_id="BIOLOGIST", assay_type="culture_prep"),
    CellAssayStep(scientist_id="BIOLOGIST", assay_type="bioassay"),
    CellAssayStep(scientist_id="TOXICOLOGIST", assay_type="cytotoxicity"),
]


_METADATA = {
    "agents": ["BIOLOGIST", "CHEMIST", "CLINICAL_LEAD", "FORMULATION_SCIENTIST", "PROJECT_DIRECTOR", "REGULATORY_SPECIALIST", "TOXICOLOGIST"],
    "resources": ["BIOLOGICAL_SAMPLES", "CELL_LAB", "FORMULATION_SUITE", "HPLC", "MASS_SPEC"],
    "agent_resources": {
        "BIOLOGIST": ["BIOLOGICAL_SAMPLES", "CELL_LAB", "HPLC"],
        "CHEMIST": ["HPLC", "MASS_SPEC"],
        "CLINICAL_LEAD": ["MASS_SPEC"],
        "FORMULATION_SCIENTIST": ["FORMULATION_SUITE"],
        "PROJECT_DIRECTOR": [],
        "REGULATORY_SPECIALIST": ["HPLC", "MASS_SPEC"],
        "TOXICOLOGIST": ["BIOLOGICAL_SAMPLES", "CELL_LAB", "HPLC", "MASS_SPEC"],
    },
    "tool_resource_map": {
        "run_hplc_analysis": ["HPLC"],
        "run_mass_spec_analysis": ["MASS_SPEC"],
        "run_cell_assay": ["BIOLOGICAL_SAMPLES", "CELL_LAB"],
        "prepare_formulation": ["FORMULATION_SUITE"],
        "verify_regulatory_compliance": [],
        "review_clinical_data": ["MASS_SPEC"],
    },
}


class DrugDiscoveryMultiRoundSim(_PharmaSim):
    """14H: Drug discovery with multi-round trials, regulatory holds, and sample counter.

    run_mass_spec_analysis is non-failing (can_fail=false); excluded from
    _DECISION_TOOLS to prevent spurious failure injection.
    """

    _DECISION_TOOLS: dict[str, float] = {
        "run_hplc_analysis": 0.2,
        "run_cell_assay": 0.3,
        "prepare_formulation": 0.2,
        "verify_regulatory_compliance": 0.2,
    }

    def __init__(self) -> None:
        super().__init__(
            hplc_steps=_HPLC_STEPS,
            mass_spec_steps=_MASS_SPEC_STEPS,
            cell_assay_steps=_CELL_ASSAY_STEPS,
            instruments=_INSTRUMENTS,
        )
        # BIOLOGICAL_SAMPLES is a Counter resource (pool of 3 units).
        # Initialize with capacity=3 so concurrent-use tracking enforces the limit.
        self.init_resource("BIOLOGICAL_SAMPLES", capacity=3)
        self._formulation_done: dict[str, bool] = {
            "FORMULATION_SCIENTIST_formulation": False,
        }
        self._clinical_review_done: dict[str, bool] = {
            "CLINICAL_LEAD_combined_review": False,
        }
        self._regulatory_done: dict[str, bool] = {
            "REGULATORY_SPECIALIST_compliance": False,
        }
        self.load_from_metadata(_METADATA)

    # -- Additional tool methods --

    def prepare_formulation(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Prepare drug formulation. Can fail."""
        if self.should_fail("prepare_formulation", agent_id):
            result = {"status": "failed", "agent": agent_id, **kwargs}
            self.log_event(agent_id, "prepare_formulation", kwargs,
                           success=False, result=result)
            return ToolResult(tool_name="prepare_formulation", success=False,
                              data=result, message="Formulation preparation failed")

        self._mark_done(self._formulation_done, agent_id, "formulation")
        result = {"status": "formulation prepared", "agent": agent_id, **kwargs}
        self.log_event(agent_id, "prepare_formulation", kwargs,
                       success=True, result=result)
        return ToolResult(tool_name="prepare_formulation", success=True,
                          data=result, message="Formulation prepared successfully")

    def review_clinical_data(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Review combined bio/tox results for clinical assessment."""
        self._mark_done(self._clinical_review_done, agent_id, "combined_review")

        result = {"status": "clinical review complete", "agent": agent_id, **kwargs}
        self.log_event(agent_id, "review_clinical_data", kwargs,
                       success=True, result=result)
        return ToolResult(tool_name="review_clinical_data", success=True,
                          data=result, message="Clinical data review complete")

    def verify_regulatory_compliance(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Verify regulatory compliance. Can reject or issue hold."""
        if self.should_fail("verify_regulatory_compliance", agent_id):
            result = {"status": "clinical_hold", "agent": agent_id, **kwargs}
            self.log_event(agent_id, "verify_regulatory_compliance", kwargs,
                           success=False, result=result)
            return ToolResult(tool_name="verify_regulatory_compliance", success=False,
                              data=result, message="Regulatory: clinical hold issued")

        self._mark_done(self._regulatory_done, agent_id, "compliance")
        result = {"status": "approved", "agent": agent_id, **kwargs}
        self.log_event(agent_id, "verify_regulatory_compliance", kwargs,
                       success=True, result=result)
        return ToolResult(tool_name="verify_regulatory_compliance", success=True,
                          data=result, message="Regulatory compliance approved")

    # -- Overrides --

    def make_tools(self) -> dict[str, Any]:
        tools = super().make_tools()
        tools["prepare_formulation"] = self.prepare_formulation
        tools["review_clinical_data"] = self.review_clinical_data
        tools["verify_regulatory_compliance"] = self.verify_regulatory_compliance
        return tools

    def is_complete(self) -> bool:
        return (super().is_complete() and
                all(self._formulation_done.values()) and
                all(self._clinical_review_done.values()) and
                all(self._regulatory_done.values()))

    @property
    def progress(self) -> dict[str, Any]:
        base = super().progress
        base["formulation"] = dict(self._formulation_done)
        base["clinical_review"] = dict(self._clinical_review_done)
        base["regulatory"] = dict(self._regulatory_done)
        base["all_complete"] = self.is_complete()
        return base
