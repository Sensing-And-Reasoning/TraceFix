"""Medical Consultation simulation config for task 5H."""

import json
from pathlib import Path

from benchmark.tools.sim_medical import (
    AnesthesiaStep,
    AssessStep,
    DiagnoseStep,
    ICUStep,
    ImagingStep,
    MedicalSim,
    OrderTestsStep,
    PrescriptionReviewStep,
    SurgeryStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "5H" / "metadata.json").read_text()
)

_RESOURCES = [
    "CT_SCANNER",
    "ICU_BEDS",
    "MRI",
    "OPERATING_ROOM",
    "VENTILATOR",
]

_ASSESS_STEPS = [
    AssessStep(agent_id="ER_DOCTOR_A", patient_id="patient_a"),
    AssessStep(agent_id="ER_DOCTOR_B", patient_id="patient_b"),
]

_ORDER_TESTS_STEPS = [
    OrderTestsStep(agent_id="ER_DOCTOR_A", patient_id="patient_a",
                   tests=["trauma_panel", "blood_type", "coag"]),
    OrderTestsStep(agent_id="ER_DOCTOR_B", patient_id="patient_b",
                   tests=["stroke_panel", "ct_angio"]),
]

_IMAGING_STEPS = [
    ImagingStep(agent_id="RADIOLOGIST", patient_id="patient_a", modality="CT"),
    ImagingStep(agent_id="RADIOLOGIST", patient_id="patient_b", modality="CT"),
    ImagingStep(agent_id="RADIOLOGIST", patient_id="patient_b", modality="MRI"),
]

_INTERPRET_IMAGING_STEPS = [
    ImagingStep(agent_id="RADIOLOGIST", patient_id="patient_a", modality="CT"),
    ImagingStep(agent_id="RADIOLOGIST", patient_id="patient_b", modality="CT"),
    ImagingStep(agent_id="RADIOLOGIST", patient_id="patient_b", modality="MRI"),
]

_DIAGNOSE_STEPS = [
    DiagnoseStep(agent_id="ER_DOCTOR_A", patient_id="patient_a"),
    DiagnoseStep(agent_id="ER_DOCTOR_B", patient_id="patient_b"),
]

_SURGERY_STEPS = [
    SurgeryStep(agent_id="SURGEON", patient_id="patient_a",
                procedure="trauma_surgery"),
]

_ANESTHESIA_STEPS = [
    AnesthesiaStep(agent_id="ANESTHESIOLOGIST", patient_id="patient_a"),
]

_ICU_STEPS = [
    ICUStep(agent_id="ICU_COORDINATOR", patient_id="patient_b"),
]

_PRESCRIPTION_REVIEW_STEPS = [
    PrescriptionReviewStep(agent_id="PHARMACIST", patient_id="patient_A_and_B"),
]


class MultiPatientTriageSim(MedicalSim):
    """5H: Multi-patient emergency triage with two ER doctors, surgeon,
    anesthesiologist, radiologist, ICU coordinator, and pharmacist.

    Imaging interpretation, diagnoses, and prescription reviews are terminal
    (each specialist runs once per patient, no retry on failure), so
    interpret_imaging/diagnose/review_prescriptions are not decision tools.
    Overriding to empty prevents --scenario/--difficulty from injecting
    failures that would leave these done-flags permanently False.
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
            surgery_steps=_SURGERY_STEPS,
            anesthesia_steps=_ANESTHESIA_STEPS,
            icu_steps=_ICU_STEPS,
            prescription_review_steps=_PRESCRIPTION_REVIEW_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
