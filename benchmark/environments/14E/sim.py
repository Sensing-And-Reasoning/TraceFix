"""Drug Discovery Pipeline simulation config for task 14E.

Four scientists share hplc + mass_spec + cell_lab.  Contains three
deadlock patterns:
  1. Reverse lock ordering — BIOLOGIST (cell_lab -> hplc) vs
     TOXICOLOGIST (hplc -> cell_lab) after receiving compound
  2. Hold-across-receive — CHEMIST uses hplc at start AND end,
     tempting to hold across wait for lead who also needs hplc
  3. TOXICOLOGIST hold-and-wait — description suggests keeping
     HPLC method loaded while moving to cell_lab
"""

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
    "agents": ["BIOLOGIST", "CHEMIST", "LEAD_SCIENTIST", "TOXICOLOGIST"],
    "resources": ["CELL_LAB", "HPLC", "MASS_SPEC"],
    "agent_resources": {
        "BIOLOGIST": ["CELL_LAB", "HPLC"],
        "CHEMIST": ["HPLC", "MASS_SPEC"],
        "LEAD_SCIENTIST": ["HPLC", "MASS_SPEC"],
        "TOXICOLOGIST": ["CELL_LAB", "HPLC", "MASS_SPEC"],
    },
    "tool_resource_map": {
        "run_hplc_analysis": ["HPLC"],
        "run_mass_spec_analysis": ["MASS_SPEC"],
        "run_cell_assay": ["CELL_LAB"],
    },
}


class DrugDiscoverySim(_PharmaSim):
    """14E: Drug discovery pipeline with three deadlock traps.

    All instrument analyses are terminal (no retry), so failure injection
    via --scenario/--difficulty is disabled.
    """

    # No retry loops: all tool outcomes are terminal (pass or fail, no redo).
    # Overriding to empty prevents --scenario/--difficulty from injecting
    # failures that would leave progress trackers permanently False.
    _DECISION_TOOLS: dict = {}

    def __init__(self) -> None:
        super().__init__(
            hplc_steps=_HPLC_STEPS,
            mass_spec_steps=_MASS_SPEC_STEPS,
            cell_assay_steps=_CELL_ASSAY_STEPS,
            instruments=_INSTRUMENTS,
        )
        self.load_from_metadata(_METADATA)
