"""Semiconductor Wafer Fabrication Line simulation config for task 15E.

Six engineers share stepper + dep_chamber + etch_chamber + metrology_station
+ monitor.  Contains five deadlock traps (four with unavoidable hold-and-wait):

  1-3. Three-way monitor contention — LITHOGRAPHER (stepper+monitor),
       DEPOSITOR (dep_chamber+monitor), ETCHER (etch_chamber+monitor)
       all require hold-and-wait because wafers cannot be ejected
       mid-process.  Simultaneous entry → deadlock on monitor.
  4.   INTEGRATION_ENGINEER stepper+metrology — holds stepper while
       acquiring metrology_station, conflicts with Phase 2 metrology.
  5.   LITHOGRAPHER double hold-and-wait — stepper+monitor AND
       etch_chamber+monitor, competing with ETCHER for etch_chamber
       and DEPOSITOR for monitor.
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
    StepperStep(engineer_id="INTEGRATION_ENGINEER", process="overlay_alignment"),
]

_DEPOSITION_STEPS = [
    DepositionStep(engineer_id="DEPOSITOR", process="cvd_growth"),
    DepositionStep(engineer_id="INTEGRATION_ENGINEER", process="film_integrity_check"),
]

_ETCH_STEPS = [
    EtchStep(engineer_id="LITHOGRAPHER", process="pattern_transfer_etch"),
    EtchStep(engineer_id="ETCHER", process="reactive_ion_etch"),
    EtchStep(engineer_id="INTEGRATION_ENGINEER", process="etch_uniformity_check"),
]

_METROLOGY_STEPS = [
    MetrologyStep(engineer_id="METROLOGY_ENGINEER", measurement="cd_measurement"),
    MetrologyStep(engineer_id="METROLOGY_ENGINEER", measurement="thickness_measurement"),
    MetrologyStep(engineer_id="METROLOGY_ENGINEER", measurement="profile_measurement"),
    MetrologyStep(engineer_id="LITHOGRAPHER", measurement="alignment_check"),
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


class SemiconductorFabSim(_SemiconductorSim):
    """15E: Semiconductor fab line with five deadlock traps.

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
