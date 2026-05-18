"""Medical Consultation simulation config for task 5E."""

import json
from pathlib import Path

from benchmark.tools.sim_medical import (
    AssessStep,
    DiagnoseStep,
    ImagingStep,
    MedicalSim,
    OrderTestsStep,
    PrescriptionReviewStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "5E" / "metadata.json").read_text()
)

_RESOURCES = ["CT_SCANNER"]

_ASSESS_STEPS = [
    AssessStep(agent_id="ER_DOCTOR", patient_id="patient_1"),
]

_ORDER_TESTS_STEPS = [
    OrderTestsStep(agent_id="ER_DOCTOR", patient_id="patient_1",
                   tests=["vitals", "basic_labs"]),
    OrderTestsStep(agent_id="CARDIOLOGIST", patient_id="patient_1",
                   tests=["ecg", "cardiac_enzymes"]),
]

_IMAGING_STEPS = [
    ImagingStep(agent_id="ER_DOCTOR", patient_id="patient_1", modality="CT"),
]

_DIAGNOSE_STEPS = [
    DiagnoseStep(agent_id="CARDIOLOGIST", patient_id="patient_1"),
]

_PRESCRIPTION_REVIEW_STEPS = [
    PrescriptionReviewStep(agent_id="PHARMACIST", patient_id="patient_1"),
]


class DualSpecialistSim(MedicalSim):
    """5E: ER doctor, cardiologist, and pharmacist consulting on a
    chest pain patient.

    Diagnoses and prescription reviews are terminal (no retry on failure), so
    diagnose/review_prescriptions are not decision tools.  Overriding to empty
    prevents --scenario/--difficulty from injecting failures that would leave
    _diagnose_done or _prescription_review_done permanently False.
    """

    # No retry loop: diagnosis and prescription review outcomes are terminal.
    _DECISION_TOOLS: dict = {}

    def __init__(self) -> None:
        super().__init__(
            assess_steps=_ASSESS_STEPS,
            order_tests_steps=_ORDER_TESTS_STEPS,
            imaging_steps=_IMAGING_STEPS,
            diagnose_steps=_DIAGNOSE_STEPS,
            prescription_review_steps=_PRESCRIPTION_REVIEW_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
