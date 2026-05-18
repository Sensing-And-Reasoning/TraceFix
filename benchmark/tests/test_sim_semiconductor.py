"""Tests for Semiconductor Fab simulation environment (task 15E)."""

import importlib

import pytest

from benchmark.tools import ToolConfig, load_tools
from benchmark.tools.sim_semiconductor import SemiconductorSim

_sim_15e = importlib.import_module("benchmark.environments.15E.sim")
SemiconductorFabSim = _sim_15e.SemiconductorFabSim


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_full_sequence(sim: SemiconductorSim):
    """Execute a correct 6-engineer full fab sequence for 15E."""
    # Stepper exposures
    sim.run_stepper_exposure("LITHOGRAPHER", "photo_exposure")
    sim.run_stepper_exposure("INTEGRATION_ENGINEER", "overlay_alignment")

    # Depositions
    sim.run_deposition("DEPOSITOR", "cvd_growth")
    sim.run_deposition("INTEGRATION_ENGINEER", "film_integrity_check")

    # Etch processes
    sim.run_etch_process("LITHOGRAPHER", "pattern_transfer_etch")
    sim.run_etch_process("ETCHER", "reactive_ion_etch")
    sim.run_etch_process("INTEGRATION_ENGINEER", "etch_uniformity_check")

    # Metrology measurements
    sim.run_metrology_measurement("METROLOGY_ENGINEER", "cd_measurement")
    sim.run_metrology_measurement("METROLOGY_ENGINEER", "thickness_measurement")
    sim.run_metrology_measurement("METROLOGY_ENGINEER", "profile_measurement")
    sim.run_metrology_measurement("LITHOGRAPHER", "alignment_check")
    sim.run_metrology_measurement("DEPOSITOR", "thickness_verification")
    sim.run_metrology_measurement("INTEGRATION_ENGINEER", "overlay_alignment")

    # Monitoring checks
    sim.check_monitoring("LITHOGRAPHER", "exposure_dose")
    sim.check_monitoring("LITHOGRAPHER", "etch_endpoint")
    sim.check_monitoring("DEPOSITOR", "deposition_rate")
    sim.check_monitoring("ETCHER", "etch_rate")
    sim.check_monitoring("PROCESS_CONTROLLER", "cross_reference")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_full_sequence_completes(self):
        sim = SemiconductorFabSim()
        _run_full_sequence(sim)
        assert sim.is_complete()
        assert not sim.has_violations

    def test_no_violations_in_events(self):
        sim = SemiconductorFabSim()
        _run_full_sequence(sim)
        for ev in sim.events:
            assert ev.violations == [], f"Unexpected violation in {ev.tool}"


# ---------------------------------------------------------------------------
# Decoupled sim: tools succeed without instrument checks
# ---------------------------------------------------------------------------

class TestDecoupledToolAccess:
    def test_stepper_succeeds_without_instrument(self):
        sim = SemiconductorFabSim()
        result = sim.run_stepper_exposure("LITHOGRAPHER", "photo_exposure")
        assert result.success
        assert not sim.has_violations

    def test_deposition_succeeds_without_instrument(self):
        sim = SemiconductorFabSim()
        result = sim.run_deposition("DEPOSITOR", "cvd_growth")
        assert result.success
        assert not sim.has_violations

    def test_etch_succeeds_without_instrument(self):
        sim = SemiconductorFabSim()
        result = sim.run_etch_process("ETCHER", "reactive_ion_etch")
        assert result.success
        assert not sim.has_violations

    def test_metrology_succeeds_without_instrument(self):
        sim = SemiconductorFabSim()
        result = sim.run_metrology_measurement("METROLOGY_ENGINEER", "cd_measurement")
        assert result.success
        assert not sim.has_violations

    def test_monitoring_succeeds_without_instrument(self):
        sim = SemiconductorFabSim()
        result = sim.check_monitoring("PROCESS_CONTROLLER", "cross_reference")
        assert result.success
        assert not sim.has_violations

    def test_unknown_instrument(self):
        sim = SemiconductorFabSim()
        result = sim.acquire_instrument("LITHOGRAPHER", "LASER_CUTTER")
        assert not result.success
        assert result.data["reason"] == "unknown_resource"

    def test_release_unknown_instrument(self):
        sim = SemiconductorFabSim()
        result = sim.release_instrument("LITHOGRAPHER", "LASER_CUTTER")
        assert not result.success
        assert result.data["reason"] == "unknown_resource"


# ---------------------------------------------------------------------------
# Instrument contention
# ---------------------------------------------------------------------------

class TestInstrumentContention:
    def test_stepper_contention(self):
        sim = SemiconductorFabSim()
        r1 = sim.acquire_instrument("LITHOGRAPHER", "STEPPER")
        r2 = sim.acquire_instrument("INTEGRATION_ENGINEER", "STEPPER")
        assert r1.data["status"] == "acquired"
        assert r2.data["status"] == "busy"
        assert not sim.has_violations

    def test_dep_chamber_contention(self):
        sim = SemiconductorFabSim()
        r1 = sim.acquire_instrument("DEPOSITOR", "DEP_CHAMBER")
        r2 = sim.acquire_instrument("INTEGRATION_ENGINEER", "DEP_CHAMBER")
        assert r1.data["status"] == "acquired"
        assert r2.data["status"] == "busy"

    def test_etch_chamber_contention(self):
        sim = SemiconductorFabSim()
        r1 = sim.acquire_instrument("ETCHER", "ETCH_CHAMBER")
        r2 = sim.acquire_instrument("LITHOGRAPHER", "ETCH_CHAMBER")
        assert r1.data["status"] == "acquired"
        assert r2.data["status"] == "busy"

    def test_metrology_station_contention(self):
        sim = SemiconductorFabSim()
        r1 = sim.acquire_instrument("METROLOGY_ENGINEER", "METROLOGY_STATION")
        r2 = sim.acquire_instrument("LITHOGRAPHER", "METROLOGY_STATION")
        assert r1.data["status"] == "acquired"
        assert r2.data["status"] == "busy"

    def test_monitor_contention(self):
        sim = SemiconductorFabSim()
        r1 = sim.acquire_instrument("LITHOGRAPHER", "MONITOR")
        r2 = sim.acquire_instrument("DEPOSITOR", "MONITOR")
        assert r1.data["status"] == "acquired"
        assert r2.data["status"] == "busy"

    def test_acquire_after_release(self):
        sim = SemiconductorFabSim()
        sim.acquire_instrument("LITHOGRAPHER", "STEPPER")
        sim.release_instrument("LITHOGRAPHER", "STEPPER")
        r = sim.acquire_instrument("INTEGRATION_ENGINEER", "STEPPER")
        assert r.data["status"] == "acquired"
        assert sim.holder_of("STEPPER") == "INTEGRATION_ENGINEER"

    def test_release_not_held(self):
        sim = SemiconductorFabSim()
        result = sim.release_instrument("LITHOGRAPHER", "STEPPER")
        assert not result.success
        assert result.data["reason"] == "resource_not_held"

    def test_release_held_by_other(self):
        sim = SemiconductorFabSim()
        sim.acquire_instrument("LITHOGRAPHER", "STEPPER")
        result = sim.release_instrument("ETCHER", "STEPPER")
        assert not result.success
        assert result.data["reason"] == "resource_not_held"
        assert sim.holder_of("STEPPER") == "LITHOGRAPHER"


# ---------------------------------------------------------------------------
# Deadlock scenarios
# ---------------------------------------------------------------------------

class TestDeadlockScenarios:
    def test_three_way_monitor_contention(self):
        """LITHOGRAPHER, DEPOSITOR, ETCHER all need MONITOR + their own chamber."""
        sim = SemiconductorFabSim()
        assert sim.try_acquire("STEPPER", "LITHOGRAPHER")
        assert sim.try_acquire("DEP_CHAMBER", "DEPOSITOR")
        assert sim.try_acquire("ETCH_CHAMBER", "ETCHER")
        # All try MONITOR — only first succeeds
        assert sim.try_acquire("MONITOR", "LITHOGRAPHER")
        assert not sim.try_acquire("MONITOR", "DEPOSITOR")
        assert not sim.try_acquire("MONITOR", "ETCHER")
        assert not sim.has_violations

    def test_stepper_metrology_deadlock(self):
        """INTEGRATION_ENGINEER holds stepper, needs metrology; METROLOGY_ENGINEER holds metrology."""
        sim = SemiconductorFabSim()
        assert sim.try_acquire("STEPPER", "INTEGRATION_ENGINEER")
        assert sim.try_acquire("METROLOGY_STATION", "METROLOGY_ENGINEER")
        # INTEGRATION_ENGINEER can't get metrology
        assert not sim.try_acquire("METROLOGY_STATION", "INTEGRATION_ENGINEER")
        assert not sim.has_violations

    def test_lithographer_double_hold_and_wait(self):
        """LITHOGRAPHER needs stepper+monitor AND etch_chamber+monitor."""
        sim = SemiconductorFabSim()
        # LITHOGRAPHER holds stepper
        assert sim.try_acquire("STEPPER", "LITHOGRAPHER")
        # ETCHER holds etch_chamber
        assert sim.try_acquire("ETCH_CHAMBER", "ETCHER")
        # DEPOSITOR holds monitor
        assert sim.try_acquire("MONITOR", "DEPOSITOR")
        # LITHOGRAPHER can't get etch_chamber or monitor
        assert not sim.try_acquire("ETCH_CHAMBER", "LITHOGRAPHER")
        assert not sim.try_acquire("MONITOR", "LITHOGRAPHER")

    def test_reverse_lock_ordering_stepper_etch(self):
        """LITHOGRAPHER: stepper->etch_chamber vs ETCHER: etch->stepper."""
        sim = SemiconductorFabSim()
        assert sim.try_acquire("STEPPER", "LITHOGRAPHER")
        assert sim.try_acquire("ETCH_CHAMBER", "ETCHER")
        assert not sim.try_acquire("ETCH_CHAMBER", "LITHOGRAPHER")
        assert not sim.try_acquire("STEPPER", "ETCHER")

    def test_dep_chamber_monitor_deadlock(self):
        """DEPOSITOR: dep_chamber->monitor vs LITHOGRAPHER: monitor->dep_chamber."""
        sim = SemiconductorFabSim()
        assert sim.try_acquire("DEP_CHAMBER", "DEPOSITOR")
        assert sim.try_acquire("MONITOR", "LITHOGRAPHER")
        assert not sim.try_acquire("MONITOR", "DEPOSITOR")
        assert not sim.try_acquire("DEP_CHAMBER", "LITHOGRAPHER")


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

class TestProgressTracking:
    def test_initial_progress(self):
        sim = SemiconductorFabSim()
        p = sim.progress
        assert p["all_complete"] is False
        assert all(not v for v in p["stepper_processes"].values())
        assert all(not v for v in p["depositions"].values())
        assert all(not v for v in p["etch_processes"].values())
        assert all(not v for v in p["metrology_measurements"].values())
        assert all(not v for v in p["monitoring_checks"].values())

    def test_progress_after_stepper(self):
        sim = SemiconductorFabSim()
        sim.run_stepper_exposure("LITHOGRAPHER", "photo_exposure")
        p = sim.progress
        assert p["stepper_processes"]["LITHOGRAPHER_photo_exposure"] is True
        assert p["all_complete"] is False

    def test_progress_after_complete(self):
        sim = SemiconductorFabSim()
        _run_full_sequence(sim)
        p = sim.progress
        assert p["all_complete"] is True
        assert all(p["stepper_processes"].values())
        assert all(p["depositions"].values())
        assert all(p["etch_processes"].values())
        assert all(p["metrology_measurements"].values())
        assert all(p["monitoring_checks"].values())

    def test_progress_per_engineer(self):
        """METROLOGY_ENGINEER has 3 measurements."""
        sim = SemiconductorFabSim()
        sim.run_metrology_measurement("METROLOGY_ENGINEER", "cd_measurement")
        sim.run_metrology_measurement("METROLOGY_ENGINEER", "thickness_measurement")
        p = sim.progress
        assert p["metrology_measurements"]["METROLOGY_ENGINEER_cd_measurement"] is True
        assert p["metrology_measurements"]["METROLOGY_ENGINEER_thickness_measurement"] is True
        assert p["metrology_measurements"]["METROLOGY_ENGINEER_profile_measurement"] is False


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    def test_load_tools_with_sim(self):
        sim = SemiconductorFabSim()
        reg = load_tools("15E", config=ToolConfig(min_delay=0, max_delay=0), sim=sim)
        assert "run_stepper_exposure" in reg.tool_names
        assert "run_deposition" in reg.tool_names
        assert "run_etch_process" in reg.tool_names
        assert "run_metrology_measurement" in reg.tool_names
        assert "check_monitoring" in reg.tool_names
        assert "acquire_instrument" not in reg.tool_names
        assert len(reg.tool_names) == 5

    def test_tools_per_agent(self):
        sim = SemiconductorFabSim()
        reg = load_tools("15E", config=ToolConfig(min_delay=0, max_delay=0), sim=sim)

        litho = reg.tools_for_agent("LITHOGRAPHER")
        assert "run_stepper_exposure" in litho
        assert "run_etch_process" in litho
        assert "run_metrology_measurement" in litho
        assert "check_monitoring" in litho
        assert "run_deposition" not in litho

        depositor = reg.tools_for_agent("DEPOSITOR")
        assert "run_deposition" in depositor
        assert "run_metrology_measurement" in depositor
        assert "check_monitoring" in depositor
        assert "run_stepper_exposure" not in depositor

        etcher = reg.tools_for_agent("ETCHER")
        assert "run_etch_process" in etcher
        assert "check_monitoring" in etcher
        assert "run_stepper_exposure" not in etcher

        metro = reg.tools_for_agent("METROLOGY_ENGINEER")
        assert "run_metrology_measurement" in metro
        assert len(metro) == 1

        controller = reg.tools_for_agent("PROCESS_CONTROLLER")
        assert "check_monitoring" in controller
        assert len(controller) == 1

        integ = reg.tools_for_agent("INTEGRATION_ENGINEER")
        assert "run_stepper_exposure" in integ
        assert "run_deposition" in integ
        assert "run_etch_process" in integ
        assert "run_metrology_measurement" in integ
        assert "check_monitoring" not in integ


# ---------------------------------------------------------------------------
# Resource requirements mapping
# ---------------------------------------------------------------------------

class TestResourceRequirements:
    def test_stepper_requires_stepper(self):
        sim = SemiconductorFabSim()
        assert sim.resource_requirements("run_stepper_exposure") == ["STEPPER"]

    def test_deposition_requires_dep_chamber(self):
        sim = SemiconductorFabSim()
        assert sim.resource_requirements("run_deposition") == ["DEP_CHAMBER"]

    def test_etch_requires_etch_chamber(self):
        sim = SemiconductorFabSim()
        assert sim.resource_requirements("run_etch_process") == ["ETCH_CHAMBER"]

    def test_metrology_requires_station(self):
        sim = SemiconductorFabSim()
        assert sim.resource_requirements("run_metrology_measurement") == ["METROLOGY_STATION"]

    def test_monitoring_requires_monitor(self):
        sim = SemiconductorFabSim()
        assert sim.resource_requirements("check_monitoring") == ["MONITOR"]
