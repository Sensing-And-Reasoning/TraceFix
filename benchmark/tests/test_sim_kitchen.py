"""Tests for kitchen simulation environment."""

import importlib

import pytest

from benchmark.tools import ToolConfig, load_tools
from benchmark.tools.sim_kitchen import KitchenSim

_sim_12e = importlib.import_module("benchmark.environments.12E.sim")
_sim_12m = importlib.import_module("benchmark.environments.12M.sim")
KitchenBasicSim = _sim_12e.KitchenBasicSim
KitchenAdvancedSim = _sim_12m.KitchenAdvancedSim


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_full_sequence_12e(sim: KitchenSim):
    """Execute a correct 3-chef sequence for 12E (progress tracking only)."""
    sim.prepare_base_dish("CHEF_A", "appetizer")
    sim.prepare_base_dish("CHEF_B", "main_course")
    sim.prepare_base_dish("CHEF_C", "dessert")

    sim.prepare_ingredient("CHEF_A", "sauce", "CHEF_C")
    sim.prepare_ingredient("CHEF_B", "garnish", "CHEF_A")
    sim.prepare_ingredient("CHEF_C", "glaze", "CHEF_B")

    sim.combine_dish("CHEF_A", "appetizer", "garnish")
    sim.combine_dish("CHEF_B", "main_course", "glaze")
    sim.combine_dish("CHEF_C", "dessert", "sauce")


def _run_full_sequence_12m(sim: KitchenSim):
    """Execute a correct 3-chef sequence for 12M (progress tracking only)."""
    sim.prepare_base_dish("CHEF_A", "appetizer")
    sim.prepare_ingredient("CHEF_A", "sauce", "CHEF_C")

    sim.prepare_base_dish("CHEF_B", "main_course")
    sim.prepare_ingredient("CHEF_B", "garnish", "CHEF_A")

    sim.prepare_base_dish("CHEF_C", "dessert")
    sim.prepare_ingredient("CHEF_C", "glaze", "CHEF_B")

    sim.combine_dish("CHEF_A", "appetizer", "garnish")
    sim.combine_dish("CHEF_B", "main_course", "glaze")
    sim.combine_dish("CHEF_C", "dessert", "sauce")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_12e_full_sequence(self):
        sim = KitchenBasicSim()
        _run_full_sequence_12e(sim)
        assert sim.is_complete()
        assert not sim.has_violations

    def test_12m_full_sequence(self):
        sim = KitchenAdvancedSim()
        _run_full_sequence_12m(sim)
        assert sim.is_complete()
        assert not sim.has_violations

    def test_no_violations_in_events(self):
        sim = KitchenBasicSim()
        _run_full_sequence_12e(sim)
        for ev in sim.events:
            assert ev.violations == [], f"Unexpected violation in {ev.tool}"


# ---------------------------------------------------------------------------
# Decoupled sim: domain tools succeed without equipment checks
# ---------------------------------------------------------------------------

class TestDecoupledToolAccess:
    def test_prepare_base_succeeds_without_equipment(self):
        """Sim tools no longer check equipment — that's the runtime layer's job."""
        sim = KitchenBasicSim()
        result = sim.prepare_base_dish("CHEF_A", "appetizer")
        assert result.success
        assert not sim.has_violations

    def test_prepare_ingredient_succeeds_without_equipment(self):
        """12M ingredient prep no longer checks equipment in sim layer."""
        sim = KitchenAdvancedSim()
        result = sim.prepare_ingredient("CHEF_A", "sauce", "CHEF_C")
        assert result.success
        assert not sim.has_violations

    def test_unknown_equipment(self):
        """acquire_equipment still validates equipment existence (sim-internal)."""
        sim = KitchenBasicSim()
        result = sim.acquire_equipment("CHEF_A", "microwave")
        assert not result.success
        assert result.data["reason"] == "unknown_resource"
        assert sim.violations[0].violation_type == "unknown_resource"

    def test_release_unknown_equipment(self):
        sim = KitchenBasicSim()
        result = sim.release_equipment("CHEF_A", "microwave")
        assert not result.success
        assert result.data["reason"] == "unknown_resource"


# ---------------------------------------------------------------------------
# Prerequisite violations
# ---------------------------------------------------------------------------

class TestPrerequisiteViolations:
    def test_combine_without_base_dish(self):
        sim = KitchenBasicSim()
        sim.prepare_ingredient("CHEF_B", "garnish", "CHEF_A")
        result = sim.combine_dish("CHEF_A", "appetizer", "garnish")
        assert not result.success
        assert result.data["reason"] == "missing_prerequisite"
        types = [v.violation_type for v in sim.violations]
        assert "missing_prerequisite" in types

    def test_combine_without_ingredient(self):
        sim = KitchenBasicSim()
        sim.acquire_equipment("CHEF_A", "STOVETOP")
        sim.acquire_equipment("CHEF_A", "OVEN")
        sim.prepare_base_dish("CHEF_A", "appetizer")
        result = sim.combine_dish("CHEF_A", "appetizer", "garnish")
        assert not result.success
        assert result.data["reason"] == "missing_prerequisite"

    def test_combine_without_both(self):
        sim = KitchenBasicSim()
        result = sim.combine_dish("CHEF_A", "appetizer", "garnish")
        assert not result.success
        assert len(sim.violations) == 2
        assert all(v.violation_type == "missing_prerequisite" for v in sim.violations)


# ---------------------------------------------------------------------------
# Release violations
# ---------------------------------------------------------------------------

class TestReleaseViolations:
    def test_release_not_held(self):
        sim = KitchenBasicSim()
        result = sim.release_equipment("CHEF_A", "OVEN")
        assert not result.success
        assert result.data["reason"] == "resource_not_held"
        assert sim.violations[0].violation_type == "resource_not_held"

    def test_release_held_by_other(self):
        sim = KitchenBasicSim()
        sim.acquire_equipment("CHEF_A", "OVEN")
        result = sim.release_equipment("CHEF_B", "OVEN")
        assert not result.success
        assert result.data["reason"] == "resource_not_held"
        assert sim.holder_of("OVEN") == "CHEF_A"


# ---------------------------------------------------------------------------
# Wrong producer
# ---------------------------------------------------------------------------

class TestWrongProducer:
    def test_wrong_ingredient_producer(self):
        """Chef B tries to prepare sauce (Chef A's job)."""
        sim = KitchenBasicSim()
        result = sim.prepare_ingredient("CHEF_B", "sauce", "CHEF_C")
        assert not result.success
        assert result.data["reason"] == "wrong_producer"
        assert sim.violations[0].violation_type == "wrong_producer"

    def test_unknown_ingredient(self):
        sim = KitchenBasicSim()
        result = sim.prepare_ingredient("CHEF_A", "ketchup", "CHEF_B")
        assert not result.success
        assert result.data["reason"] == "unknown_resource"


# ---------------------------------------------------------------------------
# Equipment contention
# ---------------------------------------------------------------------------

class TestEquipmentContention:
    def test_two_chefs_same_equipment(self):
        """Second chef gets 'busy' — not a violation."""
        sim = KitchenBasicSim()
        r1 = sim.acquire_equipment("CHEF_A", "OVEN")
        r2 = sim.acquire_equipment("CHEF_B", "OVEN")
        assert r1.data["status"] == "acquired"
        assert r2.data["status"] == "busy"
        assert r2.data["held_by"] == "CHEF_A"
        assert not sim.has_violations

    def test_acquire_after_release(self):
        sim = KitchenBasicSim()
        sim.acquire_equipment("CHEF_A", "OVEN")
        sim.release_equipment("CHEF_A", "OVEN")
        r = sim.acquire_equipment("CHEF_B", "OVEN")
        assert r.data["status"] == "acquired"
        assert sim.holder_of("OVEN") == "CHEF_B"

    def test_double_acquire_same_agent(self):
        """Agent already holds it — gets busy (held by self)."""
        sim = KitchenBasicSim()
        sim.acquire_equipment("CHEF_A", "OVEN")
        r = sim.acquire_equipment("CHEF_A", "OVEN")
        assert r.data["status"] == "busy"
        assert r.data["held_by"] == "CHEF_A"


# ---------------------------------------------------------------------------
# 12E vs 12M difference: ingredient equipment requirements
# ---------------------------------------------------------------------------

class TestTaskDifferences:
    def test_12e_ingredient_no_equipment(self):
        """In 12E, ingredient prep succeeds (no equipment check in sim)."""
        sim = KitchenBasicSim()
        result = sim.prepare_ingredient("CHEF_A", "sauce", "CHEF_C")
        assert result.success
        assert not sim.has_violations

    def test_12m_ingredient_succeeds_without_equipment(self):
        """In 12M, sim no longer checks equipment — runtime layer does that."""
        sim = KitchenAdvancedSim()
        result = sim.prepare_ingredient("CHEF_A", "sauce", "CHEF_C")
        assert result.success
        assert not sim.has_violations

    def test_12m_glaze_succeeds_without_equipment(self):
        """In 12M, glaze prep succeeds without equipment check in sim."""
        sim = KitchenAdvancedSim()
        result = sim.prepare_ingredient("CHEF_C", "glaze", "CHEF_B")
        assert result.success
        assert not sim.has_violations


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

class TestProgressTracking:
    def test_initial_progress(self):
        sim = KitchenBasicSim()
        p = sim.progress
        assert p["all_complete"] is False
        assert all(not v for v in p["base_prepared"].values())
        assert all(not v for v in p["ingredient_available"].values())
        assert all(not v for v in p["dish_completed"].values())

    def test_progress_after_base(self):
        sim = KitchenBasicSim()
        sim.acquire_equipment("CHEF_A", "STOVETOP")
        sim.acquire_equipment("CHEF_A", "OVEN")
        sim.prepare_base_dish("CHEF_A", "appetizer")
        p = sim.progress
        assert p["base_prepared"]["CHEF_A"] is True
        assert p["base_prepared"]["CHEF_B"] is False
        assert p["all_complete"] is False

    def test_progress_after_ingredient(self):
        sim = KitchenBasicSim()
        sim.prepare_ingredient("CHEF_A", "sauce", "CHEF_C")
        p = sim.progress
        assert p["ingredient_available"]["sauce"] is True
        assert p["ingredient_available"]["garnish"] is False

    def test_progress_after_complete(self):
        sim = KitchenBasicSim()
        _run_full_sequence_12e(sim)
        p = sim.progress
        assert p["all_complete"] is True
        assert all(p["base_prepared"].values())
        assert all(p["ingredient_available"].values())
        assert all(p["dish_completed"].values())


# ---------------------------------------------------------------------------
# Goal check
# ---------------------------------------------------------------------------

class TestGoalCheck:
    def test_incomplete_one_dish(self):
        """Not complete until ALL 3 dishes done."""
        sim = KitchenBasicSim()
        sim.acquire_equipment("CHEF_A", "STOVETOP")
        sim.acquire_equipment("CHEF_A", "OVEN")
        sim.prepare_base_dish("CHEF_A", "appetizer")
        sim.release_equipment("CHEF_A", "STOVETOP")
        sim.release_equipment("CHEF_A", "OVEN")
        sim.prepare_ingredient("CHEF_B", "garnish", "CHEF_A")
        sim.combine_dish("CHEF_A", "appetizer", "garnish")
        assert not sim.is_complete()

    def test_complete_all_three(self):
        sim = KitchenBasicSim()
        _run_full_sequence_12e(sim)
        assert sim.is_complete()


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------

class TestEventLogging:
    def test_events_recorded(self):
        sim = KitchenBasicSim()
        sim.acquire_equipment("CHEF_A", "OVEN")
        sim.release_equipment("CHEF_A", "OVEN")
        assert len(sim.events) == 2
        assert sim.events[0].tool == "acquire_equipment"
        assert sim.events[1].tool == "release_equipment"
        assert sim.events[0].agent == "CHEF_A"

    def test_successful_events_have_no_violations(self):
        """Sim tools succeed without equipment — no violations logged."""
        sim = KitchenBasicSim()
        sim.prepare_base_dish("CHEF_A", "appetizer")
        assert len(sim.events) == 1
        assert sim.events[0].violations == []
        assert sim.events[0].success is True


# ---------------------------------------------------------------------------
# Registry integration (sim-mode via load_tools)
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    def test_load_tools_with_sim(self):
        sim = KitchenBasicSim()
        reg = load_tools("12E", config=ToolConfig(min_delay=0, max_delay=0), sim=sim)
        assert "acquire_equipment" not in reg.tool_names
        assert "prepare_base_dish" in reg.tool_names
        assert len(reg.tool_names) == 3

    def test_sim_mode_call(self):
        """Sim-mode call returns ToolResult synchronously (not async)."""
        sim = KitchenBasicSim()
        reg = load_tools("12E", config=ToolConfig(min_delay=0, max_delay=0), sim=sim)
        result = sim.acquire_equipment("CHEF_A", "OVEN")
        assert result.success
        assert result.data["status"] == "acquired"

