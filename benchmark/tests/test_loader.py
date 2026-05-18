"""Tests for the unified benchmark loader."""

import pytest

from benchmark.loader import (
    TaskEntry,
    list_task_ids,
    load_task,
    load_tasks,
    _SCENARIO_MAP,
    _DIFFICULTY_MAP,
)


class TestListTaskIds:
    def test_returns_48_ids(self):
        ids = list_task_ids()
        assert len(ids) == 48

    def test_sorted_by_numeric_then_difficulty(self):
        ids = list_task_ids()
        # First three should be 1E, 1H, 1M sorted as E<M<H
        assert ids[0] == "1E"
        assert ids[1] == "1M"
        assert ids[2] == "1H"

    def test_all_ids_match_pattern(self):
        import re
        pattern = re.compile(r"^\d+[EMH]$")
        for tid in list_task_ids():
            assert pattern.match(tid), f"{tid} does not match expected pattern"

    def test_includes_new_scenarios(self):
        ids = list_task_ids()
        assert "12E" in ids
        assert "15E" in ids
        assert "16M" in ids


class TestLoadTask:
    def test_load_3e_fields(self):
        task = load_task("3E")
        assert isinstance(task, TaskEntry)
        assert task.task_id == "3E"
        assert task.scenario == "Research Writing"
        assert task.difficulty == "Easy"
        assert task.task_name  # non-empty
        assert "Task 3E:" not in task.task_name  # prefix stripped
        assert len(task.description) > 0
        assert isinstance(task.checklist, list)

    def test_load_3e_case_insensitive(self):
        task = load_task("3e")
        assert task.task_id == "3E"

    def test_load_12e(self):
        task = load_task("12E")
        assert task.task_id == "12E"
        assert task.scenario == "Collaborative Kitchen"
        assert task.difficulty == "Easy"
        assert task.task_name  # non-empty
        assert len(task.description) > 0

    def test_12e_has_checklist(self):
        task = load_task("12E")
        assert isinstance(task.checklist, list)
        assert len(task.checklist) > 0
        # Each checklist entry should be a dict
        for item in task.checklist:
            assert isinstance(item, dict)

    def test_3e_has_checklist(self):
        task = load_task("3E")
        # 3E now has a checklist.json in environments/
        assert isinstance(task.checklist, list)
        assert len(task.checklist) > 0

    def test_invalid_id_raises(self):
        with pytest.raises(ValueError, match="Unknown task_id"):
            load_task("99Z")

    def test_invalid_id_message_lists_available(self):
        with pytest.raises(ValueError, match="Available:"):
            load_task("0X")


class TestLoadTasks:
    def test_load_all(self):
        tasks = load_tasks()
        assert len(tasks) == 48
        assert all(isinstance(t, TaskEntry) for t in tasks)

    def test_load_subset(self):
        tasks = load_tasks(["3E", "12E"])
        assert len(tasks) == 2
        assert tasks[0].task_id == "3E"
        assert tasks[1].task_id == "12E"


class TestScenarioAndDifficultyMaps:
    def test_scenario_map_covers_1_through_16(self):
        for i in range(1, 17):
            assert str(i) in _SCENARIO_MAP

    def test_difficulty_map(self):
        assert _DIFFICULTY_MAP == {"E": "Easy", "M": "Medium", "H": "Hard"}
