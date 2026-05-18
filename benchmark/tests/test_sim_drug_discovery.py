"""Tests for Drug Discovery Pipeline simulation environment (task 14E)."""

import importlib

import pytest

from benchmark.tools import ToolConfig, load_tools
from benchmark.tools.sim_pharma import PharmaSim

_sim_14e = importlib.import_module("benchmark.environments.14E.sim")
DrugDiscoverySim = _sim_14e.DrugDiscoverySim


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_full_sequence(sim: PharmaSim):
    """Execute a correct 4-scientist full pipeline for 14E."""
    # HPLC analyses
    sim.run_hplc_analysis("CHEMIST", "synthesis_qc")
    sim.run_hplc_analysis("CHEMIST", "documentation")
    sim.run_hplc_analysis("BIOLOGIST", "stability")
    sim.run_hplc_analysis("TOXICOLOGIST", "purity_check")
    sim.run_hplc_analysis("LEAD_SCIENTIST", "structural_confirmation")

    # Mass spec analyses
    sim.run_mass_spec_analysis("CHEMIST", "molecular_id")
    sim.run_mass_spec_analysis("TOXICOLOGIST", "baseline_markers")
    sim.run_mass_spec_analysis("LEAD_SCIENTIST", "reference_methods")
    sim.run_mass_spec_analysis("LEAD_SCIENTIST", "characterization")

    # Cell assays
    sim.run_cell_assay("BIOLOGIST", "culture_prep")
    sim.run_cell_assay("BIOLOGIST", "bioassay")
    sim.run_cell_assay("TOXICOLOGIST", "cytotoxicity")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_full_pipeline_completes(self):
        sim = DrugDiscoverySim()
        _run_full_sequence(sim)
        assert sim.is_complete()
        assert not sim.has_violations

    def test_no_violations_in_events(self):
        sim = DrugDiscoverySim()
        _run_full_sequence(sim)
        for ev in sim.events:
            assert ev.violations == [], f"Unexpected violation in {ev.tool}"


# ---------------------------------------------------------------------------
# Decoupled sim: tools succeed without instrument checks
# ---------------------------------------------------------------------------

class TestDecoupledToolAccess:
    def test_hplc_succeeds_without_instrument(self):
        """Sim tools no longer check instrument state — runtime layer handles that."""
        sim = DrugDiscoverySim()
        result = sim.run_hplc_analysis("CHEMIST", "synthesis_qc")
        assert result.success
        assert not sim.has_violations

    def test_mass_spec_succeeds_without_instrument(self):
        sim = DrugDiscoverySim()
        result = sim.run_mass_spec_analysis("CHEMIST", "molecular_id")
        assert result.success
        assert not sim.has_violations

    def test_cell_assay_succeeds_without_instrument(self):
        sim = DrugDiscoverySim()
        result = sim.run_cell_assay("BIOLOGIST", "culture_prep")
        assert result.success
        assert not sim.has_violations

    def test_unknown_instrument(self):
        sim = DrugDiscoverySim()
        result = sim.acquire_instrument("CHEMIST", "NMR_SPECTROMETER")
        assert not result.success
        assert result.data["reason"] == "unknown_resource"

    def test_release_unknown_instrument(self):
        sim = DrugDiscoverySim()
        result = sim.release_instrument("CHEMIST", "NMR_SPECTROMETER")
        assert not result.success
        assert result.data["reason"] == "unknown_resource"


# ---------------------------------------------------------------------------
# Instrument contention
# ---------------------------------------------------------------------------

class TestInstrumentContention:
    def test_two_scientists_same_hplc(self):
        """Second scientist gets 'busy' — not a violation."""
        sim = DrugDiscoverySim()
        r1 = sim.acquire_instrument("CHEMIST", "HPLC")
        r2 = sim.acquire_instrument("BIOLOGIST", "HPLC")
        assert r1.data["status"] == "acquired"
        assert r2.data["status"] == "busy"
        assert r2.data["held_by"] == "CHEMIST"
        assert not sim.has_violations

    def test_mass_spec_contention(self):
        sim = DrugDiscoverySim()
        r1 = sim.acquire_instrument("CHEMIST", "MASS_SPEC")
        r2 = sim.acquire_instrument("TOXICOLOGIST", "MASS_SPEC")
        assert r1.data["status"] == "acquired"
        assert r2.data["status"] == "busy"

    def test_cell_lab_contention(self):
        sim = DrugDiscoverySim()
        r1 = sim.acquire_instrument("BIOLOGIST", "CELL_LAB")
        r2 = sim.acquire_instrument("TOXICOLOGIST", "CELL_LAB")
        assert r1.data["status"] == "acquired"
        assert r2.data["status"] == "busy"

    def test_acquire_after_release(self):
        sim = DrugDiscoverySim()
        sim.acquire_instrument("CHEMIST", "HPLC")
        sim.release_instrument("CHEMIST", "HPLC")
        r = sim.acquire_instrument("BIOLOGIST", "HPLC")
        assert r.data["status"] == "acquired"
        assert sim.holder_of("HPLC") == "BIOLOGIST"

    def test_release_not_held(self):
        sim = DrugDiscoverySim()
        result = sim.release_instrument("CHEMIST", "HPLC")
        assert not result.success
        assert result.data["reason"] == "resource_not_held"

    def test_release_held_by_other(self):
        sim = DrugDiscoverySim()
        sim.acquire_instrument("CHEMIST", "HPLC")
        result = sim.release_instrument("BIOLOGIST", "HPLC")
        assert not result.success
        assert result.data["reason"] == "resource_not_held"
        assert sim.holder_of("HPLC") == "CHEMIST"


# ---------------------------------------------------------------------------
# Deadlock scenarios
# ---------------------------------------------------------------------------

class TestDeadlockScenarios:
    def test_reverse_lock_ordering_cell_lab_hplc(self):
        """BIOLOGIST: cell_lab->hplc vs TOXICOLOGIST: hplc->cell_lab."""
        sim = DrugDiscoverySim()
        assert sim.try_acquire("CELL_LAB", "BIOLOGIST")
        assert sim.try_acquire("HPLC", "TOXICOLOGIST")
        # Both try the other — deadlock
        assert not sim.try_acquire("HPLC", "BIOLOGIST")
        assert not sim.try_acquire("CELL_LAB", "TOXICOLOGIST")
        assert not sim.has_violations

    def test_hold_across_receive_hplc(self):
        """CHEMIST holds HPLC at start and end, tempting hold-across-wait."""
        sim = DrugDiscoverySim()
        assert sim.try_acquire("HPLC", "CHEMIST")
        # LEAD_SCIENTIST also needs HPLC
        assert not sim.try_acquire("HPLC", "LEAD_SCIENTIST")
        assert sim.holder_of("HPLC") == "CHEMIST"

    def test_three_way_instrument_contention(self):
        """Three scientists compete for different instruments simultaneously."""
        sim = DrugDiscoverySim()
        assert sim.try_acquire("HPLC", "CHEMIST")
        assert sim.try_acquire("MASS_SPEC", "TOXICOLOGIST")
        assert sim.try_acquire("CELL_LAB", "BIOLOGIST")
        # All held — no one can get anyone else's instrument
        assert not sim.try_acquire("MASS_SPEC", "CHEMIST")
        assert not sim.try_acquire("CELL_LAB", "TOXICOLOGIST")
        assert not sim.try_acquire("HPLC", "BIOLOGIST")


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

class TestProgressTracking:
    def test_initial_progress(self):
        sim = DrugDiscoverySim()
        p = sim.progress
        assert p["all_complete"] is False
        assert all(not v for v in p["hplc_analyses"].values())
        assert all(not v for v in p["mass_spec_analyses"].values())
        assert all(not v for v in p["cell_assays"].values())

    def test_progress_after_hplc(self):
        sim = DrugDiscoverySim()
        sim.run_hplc_analysis("CHEMIST", "synthesis_qc")
        p = sim.progress
        assert p["hplc_analyses"]["CHEMIST_synthesis_qc"] is True
        assert p["all_complete"] is False

    def test_progress_after_complete(self):
        sim = DrugDiscoverySim()
        _run_full_sequence(sim)
        p = sim.progress
        assert p["all_complete"] is True
        assert all(p["hplc_analyses"].values())
        assert all(p["mass_spec_analyses"].values())
        assert all(p["cell_assays"].values())


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    def test_load_tools_with_sim(self):
        sim = DrugDiscoverySim()
        reg = load_tools("14E", config=ToolConfig(min_delay=0, max_delay=0), sim=sim)
        assert "run_hplc_analysis" in reg.tool_names
        assert "run_mass_spec_analysis" in reg.tool_names
        assert "run_cell_assay" in reg.tool_names
        assert "acquire_instrument" not in reg.tool_names
        assert len(reg.tool_names) == 3

    def test_tools_per_agent(self):
        sim = DrugDiscoverySim()
        reg = load_tools("14E", config=ToolConfig(min_delay=0, max_delay=0), sim=sim)

        chemist = reg.tools_for_agent("CHEMIST")
        assert "run_hplc_analysis" in chemist
        assert "run_mass_spec_analysis" in chemist
        assert "run_cell_assay" not in chemist

        biologist = reg.tools_for_agent("BIOLOGIST")
        assert "run_hplc_analysis" in biologist
        assert "run_cell_assay" in biologist
        assert "run_mass_spec_analysis" not in biologist

        toxicologist = reg.tools_for_agent("TOXICOLOGIST")
        assert "run_hplc_analysis" in toxicologist
        assert "run_mass_spec_analysis" in toxicologist
        assert "run_cell_assay" in toxicologist

        lead = reg.tools_for_agent("LEAD_SCIENTIST")
        assert "run_hplc_analysis" in lead
        assert "run_mass_spec_analysis" in lead
        assert "run_cell_assay" not in lead


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------

class TestEventLogging:
    def test_events_recorded(self):
        sim = DrugDiscoverySim()
        sim.acquire_instrument("CHEMIST", "HPLC")
        sim.release_instrument("CHEMIST", "HPLC")
        assert len(sim.events) == 2
        assert sim.events[0].tool == "acquire_instrument"
        assert sim.events[1].tool == "release_instrument"
