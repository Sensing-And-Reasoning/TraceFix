"""Pharma Lab simulation config for task 13E.

Three scientists share SPECTROMETER + CENTRIFUGE.  Contains two
deadlock patterns:
  1. Reverse lock ordering (CHEMIST: spec->cent, BIOLOGIST: cent->spec)
  2. Hold-and-wait (CHEMIST holds spec while waiting for ANALYST who needs spec)
"""

import json
from pathlib import Path

from benchmark.tools.sim_lab import (
    AnalysisStep, SeparationStep, TestStep, LabSim as _LabSim,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "13E" / "metadata.json").read_text()
)

_INSTRUMENTS = ["SPECTROMETER", "CENTRIFUGE"]

_ANALYSES = [
    AnalysisStep(scientist_id="CHEMIST", sample="raw_materials"),
    AnalysisStep(scientist_id="CHEMIST", sample="final_validation"),
    AnalysisStep(scientist_id="BIOLOGIST", sample="fluorescence"),
    AnalysisStep(scientist_id="ANALYST", sample="molecular_detail"),
]

_SEPARATIONS = [
    SeparationStep(scientist_id="CHEMIST", material="compound_purification"),
    SeparationStep(scientist_id="BIOLOGIST", material="cell_cultures"),
    SeparationStep(scientist_id="ANALYST", material="verification"),
]

_TESTS = [
    TestStep(scientist_id="BIOLOGIST", test_type="bioassay"),
]


class PharmaLabSim(_LabSim):
    """13E: Pharmaceutical lab synthesis with two deadlock traps.

    Bioassay outcome is terminal (no retry loop), so run_bioassay is not
    a decision tool — failure injection via --scenario/--difficulty is disabled.
    """

    # No retry loop: bioassay outcome is terminal regardless of pass/fail.
    # Overriding to empty prevents --scenario/--difficulty from injecting
    # failures that would leave _test_done permanently False.
    _DECISION_TOOLS: dict = {}

    def __init__(self) -> None:
        super().__init__(
            analyses=_ANALYSES,
            separations=_SEPARATIONS,
            tests=_TESTS,
            instruments=_INSTRUMENTS,
        )
        self.load_from_metadata(_METADATA)
