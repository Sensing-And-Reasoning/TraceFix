"""Cross-Calibration Semiconductor Fab simulation config for task 15M.

Extends 15E with cross-instrument calibration steps that create true
circular lock dependencies between fab agents:

Phase 1 — 3-way circular (no total ordering can fix):
  LITHOGRAPHER:  holds stepper       → needs etch_chamber   (OPC cross-cal)
  ETCHER:        holds etch_chamber  → needs dep_chamber    (endpoint cross-cal)
  DEPOSITOR:     holds dep_chamber   → needs stepper        (alignment cross-cal)

Phase 2 — 2-way circular (reverse lock ordering):
  LITHOGRAPHER:  holds stepper           → needs metrology_station  (in-situ CD)
  DEPOSITOR:     holds metrology_station → needs stepper            (reference datum)

Expected: TLC finds deadlock, requires 2+ repair iterations.
"""

from benchmark.tools.sim_base import FailureScenario
from benchmark.tools.sim_semiconductor import (
    StepperStep, DepositionStep, EtchStep,
    MetrologyStep, MonitoringStep,
    SemiconductorSim as _SemiconductorSim,
)

_INSTRUMENTS = ["STEPPER", "DEP_CHAMBER", "ETCH_CHAMBER", "METROLOGY_STATION", "MONITOR"]

_STEPPER_STEPS = [
    StepperStep(engineer_id="LITHOGRAPHER", process="photo_exposure"),
    # Cross-calibration reads by other agents
    StepperStep(engineer_id="DEPOSITOR", process="read_alignment_sensors"),
    StepperStep(engineer_id="DEPOSITOR", process="read_reference_datum"),
    StepperStep(engineer_id="INTEGRATION_ENGINEER", process="overlay_alignment"),
]

_DEPOSITION_STEPS = [
    DepositionStep(engineer_id="DEPOSITOR", process="cvd_growth"),
    # Cross-calibration reads by other agents
    DepositionStep(engineer_id="ETCHER", process="read_film_stress_sensors"),
    DepositionStep(engineer_id="INTEGRATION_ENGINEER", process="film_integrity_check"),
]

_ETCH_STEPS = [
    EtchStep(engineer_id="LITHOGRAPHER", process="pattern_transfer_etch"),
    # Cross-calibration reads by other agents
    EtchStep(engineer_id="LITHOGRAPHER", process="read_etch_profile_sensors"),
    EtchStep(engineer_id="ETCHER", process="reactive_ion_etch"),
    EtchStep(engineer_id="INTEGRATION_ENGINEER", process="etch_uniformity_check"),
]

_METROLOGY_STEPS = [
    MetrologyStep(engineer_id="METROLOGY_ENGINEER", measurement="cd_measurement"),
    MetrologyStep(engineer_id="METROLOGY_ENGINEER", measurement="thickness_measurement"),
    MetrologyStep(engineer_id="METROLOGY_ENGINEER", measurement="profile_measurement"),
    MetrologyStep(engineer_id="LITHOGRAPHER", measurement="cd_measurement"),
    MetrologyStep(engineer_id="DEPOSITOR", measurement="thickness_verification"),
    MetrologyStep(engineer_id="INTEGRATION_ENGINEER", measurement="overlay_alignment"),
]

_MONITORING_STEPS = [
    MonitoringStep(engineer_id="LITHOGRAPHER", check_type="exposure_dose"),
    MonitoringStep(engineer_id="LITHOGRAPHER", check_type="etch_endpoint"),
    MonitoringStep(engineer_id="DEPOSITOR", check_type="deposition_rate"),
    MonitoringStep(engineer_id="ETCHER", check_type="etch_rate"),
    MonitoringStep(engineer_id="PROCESS_CONTROLLER", check_type="cross_reference"),
]


class CrossCalibrationFabSim(_SemiconductorSim):
    """15M: Semiconductor fab line with cross-calibration circular deadlocks.

    No retry loops in this task: metrology, etch, and monitoring outcomes are
    terminal regardless of pass/fail.  Overriding _DECISION_TOOLS to empty
    prevents --scenario/--difficulty from injecting failures that would leave
    done-trackers permanently False.
    """

    # No retry loop: all tool outcomes are terminal.
    _DECISION_TOOLS: dict = {}

    _FAILURE_SCENARIOS: dict[str, FailureScenario] = {}

    _DEFAULT_OPTIONAL: set[str] = set()

    def __init__(self, scenario: str | None = None) -> None:
        super().__init__(
            stepper_steps=_STEPPER_STEPS,
            deposition_steps=_DEPOSITION_STEPS,
            etch_steps=_ETCH_STEPS,
            metrology_steps=_METROLOGY_STEPS,
            monitoring_steps=_MONITORING_STEPS,
            instruments=_INSTRUMENTS,
        )
        self._optional_items = set(self._DEFAULT_OPTIONAL)
        if scenario:
            self.configure_scenario(scenario)
