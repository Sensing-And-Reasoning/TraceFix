"""Medical Consultation simulation config for task 5M."""

import json
from pathlib import Path

from benchmark.tools.sim_medical import (
    AssessStep,
    CaseConferenceStep,
    DiagnoseStep,
    ImagingStep,
    MedicalSim,
    OrderTestsStep,
    PrescriptionReviewStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "5M" / "metadata.json").read_text()
)

_RESOURCES = ["CONSULTATION_ROOM", "CT_SCANNER", "MRI"]

_ASSESS_STEPS = [
    AssessStep(agent_id="ER_DOCTOR", patient_id="patient_1"),
]

_ORDER_TESTS_STEPS = [
    OrderTestsStep(agent_id="ER_DOCTOR", patient_id="patient_1",
                   tests=["vitals", "basic_labs"]),
    OrderTestsStep(agent_id="CARDIOLOGIST", patient_id="patient_1",
                   tests=["ecg", "cardiac_enzymes"]),
    OrderTestsStep(agent_id="NEUROLOGIST", patient_id="patient_1",
                   tests=["neuro_exam", "nerve_conduction"]),
]

_IMAGING_STEPS = [
    ImagingStep(agent_id="RADIOLOGIST", patient_id="patient_1", modality="CT"),
    ImagingStep(agent_id="RADIOLOGIST", patient_id="patient_1", modality="MRI"),
]

_INTERPRET_IMAGING_STEPS = [
    ImagingStep(agent_id="RADIOLOGIST", patient_id="patient_1", modality="CT"),
    ImagingStep(agent_id="RADIOLOGIST", patient_id="patient_1", modality="MRI"),
]

_DIAGNOSE_STEPS = [
    DiagnoseStep(agent_id="CARDIOLOGIST", patient_id="patient_1"),
    DiagnoseStep(agent_id="NEUROLOGIST", patient_id="patient_1"),
]

_CASE_CONFERENCE_STEPS = [
    CaseConferenceStep(agent_id="ER_DOCTOR", case_id="patient_1"),
]

_PRESCRIPTION_REVIEW_STEPS = [
    PrescriptionReviewStep(agent_id="PHARMACIST", patient_id="patient_1"),
]


class MultiSpecialtyCaseSim(MedicalSim):
    """5M: Multi-specialty case conference with ER doctor, cardiologist,
    neurologist, radiologist, and pharmacist.

    Imaging interpretation, diagnoses, and prescription reviews are terminal
    (each specialist runs once, no retry on failure), so interpret_imaging/
    diagnose/review_prescriptions are not decision tools.  Overriding to empty
    prevents --scenario/--difficulty from injecting failures that would leave
    these done-flags permanently False.
    """

    # No retry loop: all diagnostic and review outcomes are terminal.
    _DECISION_TOOLS: dict = {}

    def __init__(self) -> None:
        super().__init__(
            assess_steps=_ASSESS_STEPS,
            order_tests_steps=_ORDER_TESTS_STEPS,
            imaging_steps=_IMAGING_STEPS,
            interpret_imaging_steps=_INTERPRET_IMAGING_STEPS,
            diagnose_steps=_DIAGNOSE_STEPS,
            case_conference_steps=_CASE_CONFERENCE_STEPS,
            prescription_review_steps=_PRESCRIPTION_REVIEW_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
