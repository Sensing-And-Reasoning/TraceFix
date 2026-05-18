"""Semiconductor Fabrication with Rework and Yield Halt simulation for task 15H.

Six engineers share stepper + dep_chamber + etch_chamber + metrology_station
+ monitor, plus a wafer_slots counter (initial=2).

Extends 15M with:
  1. Rework loops — failed metrology triggers re-fab (costs wafer_slot)
  2. Contamination check — INTEGRATION_ENGINEER acquires dep_chamber + etch_chamber
     + stepper atomically (3-lock acquire, deadlock risk)
  3. Yield halt — PROCESS_CONTROLLER acquires monitor + metrology_station, broadcasts
     halt; all fab agents must release instruments and wait
  4. 3-way circular from 15M still present
  5. Counter limits concurrent fabrication (wafer_slots=2)
"""

from benchmark.tools.sim_base import FailureScenario, FailureSpec
from benchmark.tools.sim_semiconductor import (
    StepperStep, DepositionStep, EtchStep,
    MetrologyStep, MonitoringStep,
    SemiconductorSim as _SemiconductorSim,
)

_INSTRUMENTS = ["STEPPER", "DEP_CHAMBER", "ETCH_CHAMBER", "METROLOGY_STATION", "MONITOR"]

_STEPPER_STEPS = [
    StepperStep(engineer_id="LITHOGRAPHER", process="photo_exposure"),
    StepperStep(engineer_id="DEPOSITOR", process="read_alignment_sensors"),
    StepperStep(engineer_id="DEPOSITOR", process="read_reference_datum"),
    StepperStep(engineer_id="INTEGRATION_ENGINEER", process="overlay_alignment"),
    StepperStep(engineer_id="INTEGRATION_ENGINEER", process="contamination_scan"),
]

_DEPOSITION_STEPS = [
    DepositionStep(engineer_id="DEPOSITOR", process="cvd_growth"),
    DepositionStep(engineer_id="ETCHER", process="read_film_stress_sensors"),
    DepositionStep(engineer_id="INTEGRATION_ENGINEER", process="film_integrity_check"),
    DepositionStep(engineer_id="INTEGRATION_ENGINEER", process="contamination_scan"),
]

_ETCH_STEPS = [
    EtchStep(engineer_id="LITHOGRAPHER", process="pattern_transfer_etch"),
    EtchStep(engineer_id="LITHOGRAPHER", process="read_etch_profile_sensors"),
    EtchStep(engineer_id="ETCHER", process="reactive_ion_etch"),
    EtchStep(engineer_id="INTEGRATION_ENGINEER", process="etch_uniformity_check"),
    EtchStep(engineer_id="INTEGRATION_ENGINEER", process="contamination_scan"),
]

_METROLOGY_STEPS = [
    MetrologyStep(engineer_id="METROLOGY_ENGINEER", measurement="cd_measurement"),
    MetrologyStep(engineer_id="METROLOGY_ENGINEER", measurement="thickness_measurement"),
    MetrologyStep(engineer_id="METROLOGY_ENGINEER", measurement="profile_measurement"),
    MetrologyStep(engineer_id="LITHOGRAPHER", measurement="cd_measurement"),
    MetrologyStep(engineer_id="DEPOSITOR", measurement="thickness_verification"),
    MetrologyStep(engineer_id="INTEGRATION_ENGINEER", measurement="overlay_alignment"),
    MetrologyStep(engineer_id="PROCESS_CONTROLLER", measurement="yield_halt_measurement"),
]

_MONITORING_STEPS = [
    MonitoringStep(engineer_id="LITHOGRAPHER", check_type="exposure_dose"),
    MonitoringStep(engineer_id="LITHOGRAPHER", check_type="etch_endpoint"),
    MonitoringStep(engineer_id="DEPOSITOR", check_type="deposition_rate"),
    MonitoringStep(engineer_id="ETCHER", check_type="etch_rate"),
    MonitoringStep(engineer_id="PROCESS_CONTROLLER", check_type="cross_reference"),
    MonitoringStep(engineer_id="PROCESS_CONTROLLER", check_type="yield_investigation"),
]


class SemiconductorFabReworkSim(_SemiconductorSim):
    """15H: Semiconductor fab with rework loops, contamination check, yield halt, and wafer_slots counter."""

    _FAILURE_SCENARIOS: dict[str, FailureScenario] = {
        "metro_fail": FailureScenario(
            name="metro_fail",
            failures=[FailureSpec("run_metrology_measurement", "METROLOGY_ENGINEER", call_index=0)],
            description="First metrology measurement fails, triggering rework",
        ),
        "etch_fail": FailureScenario(
            name="etch_fail",
            failures=[FailureSpec("run_etch_process", "ETCHER", call_index=0)],
            description="First etch process fails, triggering rework",
        ),
        "yield_halt": FailureScenario(
            name="yield_halt",
            failures=[FailureSpec("check_monitoring", "PROCESS_CONTROLLER", call_index=0)],
            description="Cross-reference check fails, triggering yield halt investigation",
        ),
    }

    _DEFAULT_OPTIONAL: set[str] = {
        "PROCESS_CONTROLLER_yield_investigation",
        "PROCESS_CONTROLLER_yield_halt_measurement",
    }

    def __init__(self, scenario: str | None = None) -> None:
        super().__init__(
            stepper_steps=_STEPPER_STEPS,
            deposition_steps=_DEPOSITION_STEPS,
            etch_steps=_ETCH_STEPS,
            metrology_steps=_METROLOGY_STEPS,
            monitoring_steps=_MONITORING_STEPS,
            instruments=_INSTRUMENTS,
        )
        # WAFER_SLOTS is a Counter resource (capacity=2): only 2 wafers can be
        # processed simultaneously.  Registered separately from mutex instruments.
        self.init_resource("WAFER_SLOTS", capacity=2)
        self._optional_items = set(self._DEFAULT_OPTIONAL)
        if scenario == "yield_halt":
            # yield_investigation and yield_halt_measurement become required
            self._optional_items.discard("PROCESS_CONTROLLER_yield_investigation")
            self._optional_items.discard("PROCESS_CONTROLLER_yield_halt_measurement")
            # cross_reference is injected to fail, so mark optional
            self._optional_items.add("PROCESS_CONTROLLER_cross_reference")
        if scenario:
            self.configure_scenario(scenario)
