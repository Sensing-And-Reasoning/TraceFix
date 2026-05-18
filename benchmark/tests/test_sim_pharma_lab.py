"""Tests for Pharmaceutical Lab simulation environment (task 13E)."""

import importlib

import pytest

from benchmark.tools import ToolConfig, load_tools
from benchmark.tools.sim_lab import LabSim

_sim_13e = importlib.import_module("benchmark.environments.13E.sim")
PharmaLabSim = _sim_13e.PharmaLabSim


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_full_sequence(sim: LabSim):
    """Execute a correct 3-scientist full lab sequence for 13E."""
    # CHEMIST analyses
    sim.run_analysis("CHEMIST", "raw_materials")
    sim.run_analysis("CHEMIST", "final_validation")
    # BIOLOGIST analysis
    sim.run_analysis("BIOLOGIST", "fluorescence")
    # ANALYST analysis
    sim.run_analysis("ANALYST", "molecular_detail")

    # Separations
    sim.run_separation("CHEMIST", "compound_purification")
    sim.run_separation("BIOLOGIST", "cell_cultures")
    sim.run_separation("ANALYST", "verification")

    # Bioassay
    sim.run_bioassay("BIOLOGIST", "test_compound")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_full_sequence_completes(self):
        sim = PharmaLabSim()
        _run_full_sequence(sim)
        assert sim.is_complete()
        assert not sim.has_violations

    def test_no_violations_in_events(self):
        sim = PharmaLabSim()
        _run_full_sequence(sim)
        for ev in sim.events:
            assert ev.violations == [], f"Unexpected violation in {ev.tool}"


# ---------------------------------------------------------------------------
# Decoupled sim: tools succeed without instrument checks
# ---------------------------------------------------------------------------

class TestDecoupledToolAccess:
    def test_analysis_succeeds_without_instrument(self):
        """Sim tools no longer check instrument state — runtime layer handles that."""
        sim = PharmaLabSim()
        result = sim.run_analysis("CHEMIST", "raw_materials")
        assert result.success
        assert not sim.has_violations

    def test_separation_succeeds_without_instrument(self):
        sim = PharmaLabSim()
        result = sim.run_separation("CHEMIST", "compound_purification")
        assert result.success
        assert not sim.has_violations

    def test_bioassay_succeeds_without_instrument(self):
        sim = PharmaLabSim()
        result = sim.run_bioassay("BIOLOGIST", "test_compound")
        assert result.success
        assert not sim.has_violations

    def test_unknown_instrument(self):
        """acquire_instrument still validates instrument existence."""
        sim = PharmaLabSim()
        result = sim.acquire_instrument("CHEMIST", "MICROSCOPE")
        assert not result.success
        assert result.data["reason"] == "unknown_resource"
        assert sim.violations[0].violation_type == "unknown_resource"

    def test_release_unknown_instrument(self):
        sim = PharmaLabSim()
        result = sim.release_instrument("CHEMIST", "MICROSCOPE")
        assert not result.success
        assert result.data["reason"] == "unknown_resource"


# ---------------------------------------------------------------------------
# Instrument contention
# ---------------------------------------------------------------------------

class TestInstrumentContention:
    def test_two_scientists_same_instrument(self):
        """Second scientist gets 'busy' — not a violation."""
        sim = PharmaLabSim()
        r1 = sim.acquire_instrument("CHEMIST", "SPECTROMETER")
        r2 = sim.acquire_instrument("BIOLOGIST", "SPECTROMETER")
        assert r1.data["status"] == "acquired"
        assert r2.data["status"] == "busy"
        assert r2.data["held_by"] == "CHEMIST"
        assert not sim.has_violations

    def test_acquire_after_release(self):
        sim = PharmaLabSim()
        sim.acquire_instrument("CHEMIST", "SPECTROMETER")
        sim.release_instrument("CHEMIST", "SPECTROMETER")
        r = sim.acquire_instrument("BIOLOGIST", "SPECTROMETER")
        assert r.data["status"] == "acquired"
        assert sim.holder_of("SPECTROMETER") == "BIOLOGIST"

    def test_double_acquire_same_agent(self):
        sim = PharmaLabSim()
        sim.acquire_instrument("CHEMIST", "CENTRIFUGE")
        r = sim.acquire_instrument("CHEMIST", "CENTRIFUGE")
        assert r.data["status"] == "busy"
        assert r.data["held_by"] == "CHEMIST"

    def test_release_not_held(self):
        sim = PharmaLabSim()
        result = sim.release_instrument("CHEMIST", "SPECTROMETER")
        assert not result.success
        assert result.data["reason"] == "resource_not_held"
        assert sim.violations[0].violation_type == "resource_not_held"

    def test_release_held_by_other(self):
        sim = PharmaLabSim()
        sim.acquire_instrument("CHEMIST", "SPECTROMETER")
        result = sim.release_instrument("BIOLOGIST", "SPECTROMETER")
        assert not result.success
        assert result.data["reason"] == "resource_not_held"
        assert sim.holder_of("SPECTROMETER") == "CHEMIST"


# ---------------------------------------------------------------------------
# Deadlock scenarios
# ---------------------------------------------------------------------------

class TestDeadlockScenarios:
    def test_reverse_lock_ordering(self):
        """CHEMIST: spec->cent vs BIOLOGIST: cent->spec → deadlock."""
        sim = PharmaLabSim()
        # CHEMIST acquires SPECTROMETER first
        assert sim.try_acquire("SPECTROMETER", "CHEMIST")
        # BIOLOGIST acquires CENTRIFUGE first
        assert sim.try_acquire("CENTRIFUGE", "BIOLOGIST")
        # Now both try the other — deadlock
        assert not sim.try_acquire("CENTRIFUGE", "CHEMIST")
        assert not sim.try_acquire("SPECTROMETER", "BIOLOGIST")
        assert not sim.has_violations  # contention, not violation

    def test_hold_and_wait_three_way(self):
        """CHEMIST holds spec while ANALYST needs spec."""
        sim = PharmaLabSim()
        assert sim.try_acquire("SPECTROMETER", "CHEMIST")
        assert not sim.try_acquire("SPECTROMETER", "ANALYST")
        assert sim.holder_of("SPECTROMETER") == "CHEMIST"


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

class TestProgressTracking:
    def test_initial_progress(self):
        sim = PharmaLabSim()
        p = sim.progress
        assert p["all_complete"] is False
        assert all(not v for v in p["analyses"].values())
        assert all(not v for v in p["separations"].values())

    def test_progress_after_analysis(self):
        sim = PharmaLabSim()
        sim.run_analysis("CHEMIST", "raw_materials")
        p = sim.progress
        assert p["analyses"]["CHEMIST_raw_materials"] is True
        assert p["all_complete"] is False

    def test_progress_after_complete(self):
        sim = PharmaLabSim()
        _run_full_sequence(sim)
        p = sim.progress
        assert p["all_complete"] is True
        assert all(p["analyses"].values())
        assert all(p["separations"].values())


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    def test_load_tools_with_sim(self):
        sim = PharmaLabSim()
        reg = load_tools("13E", config=ToolConfig(min_delay=0, max_delay=0), sim=sim)
        assert "run_analysis" in reg.tool_names
        assert "run_separation" in reg.tool_names
        assert "run_bioassay" in reg.tool_names
        assert "acquire_instrument" not in reg.tool_names
        assert len(reg.tool_names) == 3

    def test_tools_per_agent(self):
        sim = PharmaLabSim()
        reg = load_tools("13E", config=ToolConfig(min_delay=0, max_delay=0), sim=sim)

        chemist = reg.tools_for_agent("CHEMIST")
        assert "run_analysis" in chemist
        assert "run_separation" in chemist
        assert "run_bioassay" not in chemist

        biologist = reg.tools_for_agent("BIOLOGIST")
        assert "run_analysis" in biologist
        assert "run_bioassay" in biologist

        analyst = reg.tools_for_agent("ANALYST")
        assert "run_analysis" in analyst
        assert "run_separation" in analyst
        assert "run_bioassay" not in analyst


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------

class TestEventLogging:
    def test_events_recorded(self):
        sim = PharmaLabSim()
        sim.acquire_instrument("CHEMIST", "SPECTROMETER")
        sim.release_instrument("CHEMIST", "SPECTROMETER")
        assert len(sim.events) == 2
        assert sim.events[0].tool == "acquire_instrument"
        assert sim.events[1].tool == "release_instrument"
        assert sim.events[0].agent == "CHEMIST"
