"""Parameterized medical consultation simulation (scenarios 5E/5M/5H)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._base import ToolResult
from .sim_base import SimContext


@dataclass
class AssessStep:
    """A patient assessment step."""

    agent_id: str
    patient_id: str


@dataclass
class OrderTestsStep:
    """A test ordering step."""

    agent_id: str
    patient_id: str
    tests: list[str]


@dataclass
class ImagingStep:
    """An imaging step (perform or interpret)."""

    agent_id: str
    patient_id: str
    modality: str  # e.g. "CT", "MRI", "X-ray"


@dataclass
class DiagnoseStep:
    """A diagnosis step."""

    agent_id: str
    patient_id: str


@dataclass
class PrescriptionReviewStep:
    """A prescription review step."""

    agent_id: str
    patient_id: str


@dataclass
class CaseConferenceStep:
    """A case conference step."""

    agent_id: str
    case_id: str


@dataclass
class SurgeryStep:
    """A surgery step."""

    agent_id: str
    patient_id: str
    procedure: str


@dataclass
class AnesthesiaStep:
    """An anesthesia preparation step."""

    agent_id: str
    patient_id: str


@dataclass
class ICUStep:
    """An ICU management step."""

    agent_id: str
    patient_id: str


class MedicalSim(SimContext):
    """Simulation for multi-agent medical consultation.

    Tracks per-agent progress through assessment, testing, imaging,
    diagnosis, surgery, and ICU management phases.  Detects violations
    such as accessing patient records or equipment without holding
    the required resource.

    Args:
        assess_steps: Patient assessment steps (need patient_record).
        order_tests_steps: Test ordering steps (need patient_record).
        imaging_steps: Imaging steps (need imaging_suite).
        interpret_imaging_steps: Imaging interpretation steps (need imaging_suite).
        diagnose_steps: Diagnosis steps (need patient_record).
        prescription_review_steps: Prescription review steps (need pharmacy).
        case_conference_steps: Case conference steps (no resource).
        surgery_steps: Surgery steps (need operating_room).
        anesthesia_steps: Anesthesia prep steps (need operating_room).
        icu_steps: ICU management steps (need icu).
        resources: List of shared resource names.
    """

    def __init__(
        self,
        assess_steps: list[AssessStep] | None = None,
        order_tests_steps: list[OrderTestsStep] | None = None,
        imaging_steps: list[ImagingStep] | None = None,
        interpret_imaging_steps: list[ImagingStep] | None = None,
        diagnose_steps: list[DiagnoseStep] | None = None,
        prescription_review_steps: list[PrescriptionReviewStep] | None = None,
        case_conference_steps: list[CaseConferenceStep] | None = None,
        surgery_steps: list[SurgeryStep] | None = None,
        anesthesia_steps: list[AnesthesiaStep] | None = None,
        icu_steps: list[ICUStep] | None = None,
        resources: list[str] | None = None,
    ) -> None:
        super().__init__()

        self._assess_steps = {f"{s.agent_id}_{s.patient_id}": s for s in (assess_steps or [])}
        self._order_tests_steps = {f"{s.agent_id}_{s.patient_id}": s for s in (order_tests_steps or [])}
        self._imaging_steps = {f"{s.agent_id}_{s.patient_id}_{s.modality}": s for s in (imaging_steps or [])}
        self._interpret_imaging_steps = {f"{s.agent_id}_{s.patient_id}_{s.modality}": s for s in (interpret_imaging_steps or [])}
        self._diagnose_steps = {f"{s.agent_id}_{s.patient_id}": s for s in (diagnose_steps or [])}
        self._prescription_review_steps = {f"{s.agent_id}_{s.patient_id}": s for s in (prescription_review_steps or [])}
        self._case_conference_steps = {f"{s.agent_id}_{s.case_id}": s for s in (case_conference_steps or [])}
        self._surgery_steps = {f"{s.agent_id}_{s.patient_id}_{s.procedure}": s for s in (surgery_steps or [])}
        self._anesthesia_steps = {f"{s.agent_id}_{s.patient_id}": s for s in (anesthesia_steps or [])}
        self._icu_steps = {f"{s.agent_id}_{s.patient_id}": s for s in (icu_steps or [])}

        self._assess_done: dict[str, bool] = {k: False for k in self._assess_steps}
        self._order_tests_done: dict[str, bool] = {k: False for k in self._order_tests_steps}
        self._imaging_done: dict[str, bool] = {k: False for k in self._imaging_steps}
        self._interpret_imaging_done: dict[str, bool] = {k: False for k in self._interpret_imaging_steps}
        self._diagnose_done: dict[str, bool] = {k: False for k in self._diagnose_steps}
        self._prescription_review_done: dict[str, bool] = {k: False for k in self._prescription_review_steps}
        self._case_conference_done: dict[str, bool] = {k: False for k in self._case_conference_steps}
        self._surgery_done: dict[str, bool] = {k: False for k in self._surgery_steps}
        self._anesthesia_done: dict[str, bool] = {k: False for k in self._anesthesia_steps}
        self._icu_done: dict[str, bool] = {k: False for k in self._icu_steps}

        for res in (resources or []):
            self.init_resource(res)

    # -- Decision tools (probabilistic failure for either/or branches) --

    _DECISION_TOOLS: dict[str, float] = {
        "interpret_imaging": 0.2,
        "diagnose": 0.2,
        "review_prescriptions": 0.3,
    }

    # -- Resource requirements --

    _TOOL_RESOURCES: dict[str, list[str]] = {
        "assess_patient": ["PATIENT_RECORD"],
        "order_tests": ["PATIENT_RECORD"],
        "perform_imaging": ["IMAGING_SUITE"],
        "interpret_imaging": ["IMAGING_SUITE"],
        "diagnose": ["PATIENT_RECORD"],
        "review_prescriptions": ["PHARMACY"],
        "conduct_case_conference": [],
        "perform_surgery": ["OPERATING_ROOM"],
        "prepare_anesthesia": ["OPERATING_ROOM"],
        "manage_icu": ["ICU"],
    }

    # Modality → IR resource name mapping for imaging tools.
    _MODALITY_RESOURCES: dict[str, str] = {
        "CT": "CT_SCANNER",
        "MRI": "MRI",
    }

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        # Prefer metadata-driven map (loaded via load_from_metadata) when available.
        if self._tool_resource_map:
            base = super().resource_requirements(tool_name, **kwargs)
            # For imaging tools, resolve modality-specific resource dynamically.
            if tool_name in ("perform_imaging", "interpret_imaging"):
                modality = str(kwargs.get("modality", "")).upper()
                res = self._MODALITY_RESOURCES.get(modality)
                if res:
                    return [res]
            return base
        return list(self._TOOL_RESOURCES.get(tool_name, []))

    # -- Simulated delays --

    _TOOL_DELAYS: dict[str, tuple[float, float]] = {
        "assess_patient": (0.5, 1.5),
        "order_tests": (0.5, 1.0),
        "perform_imaging": (2.0, 5.0),
        "interpret_imaging": (1.0, 3.0),
        "diagnose": (1.0, 2.0),
        "review_prescriptions": (0.5, 1.5),
        "conduct_case_conference": (2.0, 4.0),
        "perform_surgery": (5.0, 10.0),
        "prepare_anesthesia": (1.0, 3.0),
        "manage_icu": (1.0, 2.0),
    }

    def tool_delay(self, tool_name: str, **kwargs: Any) -> tuple[float, float]:
        return self._TOOL_DELAYS.get(tool_name, (0.0, 0.0))

    # -- Tool implementations --

    def assess_patient(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Assess a patient. No shared resource required."""
        patient_id = kwargs.get("patient_id", "unknown")

        self._mark_done(self._assess_done, agent_id, patient_id)

        result = {"patient_id": patient_id, "status": "assessed", "agent": agent_id}
        self.log_event(agent_id, "assess_patient", {"patient_id": patient_id},
                       success=True, result=result)
        return ToolResult(tool_name="assess_patient", success=True,
                          data=result, message=f"Patient assessed: {patient_id}")

    def order_tests(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Order tests. No shared resource required."""
        patient_id = kwargs.get("patient_id", "unknown")
        tests = kwargs.get("tests", [])

        self._mark_done(self._order_tests_done, agent_id, patient_id)

        result = {"patient_id": patient_id, "tests": tests, "status": "ordered", "agent": agent_id}
        self.log_event(agent_id, "order_tests", {"patient_id": patient_id, "tests": tests},
                       success=True, result=result)
        return ToolResult(tool_name="order_tests", success=True,
                          data=result, message=f"Tests ordered for {patient_id}: {', '.join(tests) if tests else 'standard panel'}")

    def perform_imaging(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Perform imaging. Requires the modality-specific scanner (CT_SCANNER or MRI)."""
        patient_id = kwargs.get("patient_id", "unknown")
        modality = kwargs.get("modality", "unknown")

        self._mark_done(self._imaging_done, agent_id, f"{patient_id}_{modality}")

        result = {"patient_id": patient_id, "modality": modality, "status": "completed", "agent": agent_id}
        self.log_event(agent_id, "perform_imaging", {"patient_id": patient_id, "modality": modality},
                       success=True, result=result)
        return ToolResult(tool_name="perform_imaging", success=True,
                          data=result, message=f"Imaging completed: {modality} for {patient_id}")

    def interpret_imaging(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Interpret imaging results. Requires the modality-specific scanner (CT_SCANNER or MRI)."""
        patient_id = kwargs.get("patient_id", "unknown")
        modality = kwargs.get("modality", "unknown")

        if self.should_fail("interpret_imaging", agent_id):
            result = {"patient_id": patient_id, "modality": modality, "status": "inconclusive", "agent": agent_id}
            self.log_event(agent_id, "interpret_imaging", {"patient_id": patient_id, "modality": modality},
                           success=False, result=result)
            return ToolResult(tool_name="interpret_imaging", success=False,
                              data=result, message=f"Imaging inconclusive: {modality} for {patient_id}")

        self._mark_done(self._interpret_imaging_done, agent_id, f"{patient_id}_{modality}")

        result = {"patient_id": patient_id, "modality": modality, "status": "interpreted", "agent": agent_id}
        self.log_event(agent_id, "interpret_imaging", {"patient_id": patient_id, "modality": modality},
                       success=True, result=result)
        return ToolResult(tool_name="interpret_imaging", success=True,
                          data=result, message=f"Imaging interpreted: {modality} for {patient_id}")

    def diagnose(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Make a diagnosis. No shared resource required."""
        patient_id = kwargs.get("patient_id", "unknown")

        if self.should_fail("diagnose", agent_id):
            result = {"patient_id": patient_id, "status": "inconclusive", "agent": agent_id}
            self.log_event(agent_id, "diagnose", {"patient_id": patient_id},
                           success=False, result=result)
            return ToolResult(tool_name="diagnose", success=False,
                              data=result, message=f"Diagnosis inconclusive for: {patient_id}")

        self._mark_done(self._diagnose_done, agent_id, patient_id)

        result = {"patient_id": patient_id, "status": "diagnosed", "agent": agent_id}
        self.log_event(agent_id, "diagnose", {"patient_id": patient_id},
                       success=True, result=result)
        return ToolResult(tool_name="diagnose", success=True,
                          data=result, message=f"Diagnosis made for: {patient_id}")

    def review_prescriptions(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Review prescriptions. No shared resource required."""
        patient_id = kwargs.get("patient_id", "unknown")

        if self.should_fail("review_prescriptions", agent_id):
            result = {"patient_id": patient_id, "status": "flagged", "agent": agent_id}
            self.log_event(agent_id, "review_prescriptions", {"patient_id": patient_id},
                           success=False, result=result)
            return ToolResult(tool_name="review_prescriptions", success=False,
                              data=result, message=f"Prescription flagged for review: {patient_id}")

        self._mark_done(self._prescription_review_done, agent_id, patient_id)

        result = {"patient_id": patient_id, "status": "reviewed", "agent": agent_id}
        self.log_event(agent_id, "review_prescriptions", {"patient_id": patient_id},
                       success=True, result=result)
        return ToolResult(tool_name="review_prescriptions", success=True,
                          data=result, message=f"Prescriptions reviewed for: {patient_id}")

    def conduct_case_conference(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Conduct a case conference. Requires CONSULTATION_ROOM when configured via metadata."""
        case_id = self._get_param(kwargs, "case_id", "patient_id")

        self._mark_done(self._case_conference_done, agent_id, case_id)

        result = {"case_id": case_id, "status": "conference held", "agent": agent_id}
        self.log_event(agent_id, "conduct_case_conference", {"case_id": case_id},
                       success=True, result=result)
        return ToolResult(tool_name="conduct_case_conference", success=True,
                          data=result, message=f"Case conference held: {case_id}")

    def perform_surgery(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Perform surgery. Requires the OPERATING_ROOM resource."""
        patient_id = kwargs.get("patient_id", "unknown")
        procedure = kwargs.get("procedure", "unknown")

        self._mark_done(self._surgery_done, agent_id, f"{patient_id}_{procedure}")

        result = {"patient_id": patient_id, "procedure": procedure, "status": "completed", "agent": agent_id}
        self.log_event(agent_id, "perform_surgery", {"patient_id": patient_id, "procedure": procedure},
                       success=True, result=result)
        return ToolResult(tool_name="perform_surgery", success=True,
                          data=result, message=f"Surgery completed: {procedure} for {patient_id}")

    def prepare_anesthesia(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Prepare anesthesia. Requires the OPERATING_ROOM resource."""
        patient_id = kwargs.get("patient_id", "unknown")

        self._mark_done(self._anesthesia_done, agent_id, patient_id)

        result = {"patient_id": patient_id, "status": "anesthesia prepared", "agent": agent_id}
        self.log_event(agent_id, "prepare_anesthesia", {"patient_id": patient_id},
                       success=True, result=result)
        return ToolResult(tool_name="prepare_anesthesia", success=True,
                          data=result, message=f"Anesthesia prepared for: {patient_id}")

    def manage_icu(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Manage ICU patient. No domain resource required (ICU_BEDS counter managed via coordination protocol)."""
        patient_id = kwargs.get("patient_id", "unknown")

        self._mark_done(self._icu_done, agent_id, patient_id)

        result = {"patient_id": patient_id, "status": "icu managed", "agent": agent_id}
        self.log_event(agent_id, "manage_icu", {"patient_id": patient_id},
                       success=True, result=result)
        return ToolResult(tool_name="manage_icu", success=True,
                          data=result, message=f"ICU managed for: {patient_id}")

    # -- SimContext interface --

    def make_tools(self) -> dict[str, Any]:
        return {
            "assess_patient": self.assess_patient,
            "order_tests": self.order_tests,
            "perform_imaging": self.perform_imaging,
            "interpret_imaging": self.interpret_imaging,
            "diagnose": self.diagnose,
            "review_prescriptions": self.review_prescriptions,
            "conduct_case_conference": self.conduct_case_conference,
            "perform_surgery": self.perform_surgery,
            "prepare_anesthesia": self.prepare_anesthesia,
            "manage_icu": self.manage_icu,
        }

    def is_complete(self) -> bool:
        return (all(self._assess_done.values()) and
                all(self._order_tests_done.values()) and
                all(self._imaging_done.values()) and
                all(self._interpret_imaging_done.values()) and
                all(self._diagnose_done.values()) and
                all(self._prescription_review_done.values()) and
                all(self._case_conference_done.values()) and
                all(self._surgery_done.values()) and
                all(self._anesthesia_done.values()) and
                all(self._icu_done.values()))

    @property
    def progress(self) -> dict[str, Any]:
        return {
            "assessments": dict(self._assess_done),
            "test_orders": dict(self._order_tests_done),
            "imaging": dict(self._imaging_done),
            "imaging_interpretations": dict(self._interpret_imaging_done),
            "diagnoses": dict(self._diagnose_done),
            "prescription_reviews": dict(self._prescription_review_done),
            "case_conferences": dict(self._case_conference_done),
            "surgeries": dict(self._surgery_done),
            "anesthesia_preps": dict(self._anesthesia_done),
            "icu_management": dict(self._icu_done),
            "all_complete": self.is_complete(),
        }
