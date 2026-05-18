"""Tests for tracefix.runtime.monitoring.result_saver."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tracefix.runtime.monitoring.result_saver import build_run_result_data, save_run_result


# --- Lightweight stubs (avoid importing full tracefix.runtime.monitoring machinery) ---

@dataclass
class _ToolCall:
    round: int
    tool_name: str
    arguments: dict
    result: dict
    elapsed: float
    timestamp: float = 0.0


@dataclass
class _AgentResult:
    agent_id: str
    steps: int
    status: str
    duration: float = 1.0
    error: str | None = None
    trace: list[_ToolCall] = field(default_factory=list)


@dataclass
class _RunResult:
    success: bool
    agent_results: list[_AgentResult]
    duration: float
    error: str | None = None


@dataclass
class _TraceEntry:
    agent: str
    operation: str
    target: str
    label: str | None = None


@dataclass
class _StateViolation:
    agent: str
    current_state: str
    operation: str
    args: dict
    valid_actions: list[dict]
    timestamp: float


@dataclass
class _Violation:
    timestamp: float
    agent: str
    tool: str
    violation_type: str
    message: str


@dataclass
class _SimEvent:
    timestamp: float
    agent: str
    tool: str
    args: dict
    success: bool
    result: dict
    violations: list[_Violation] = field(default_factory=list)


class _FakeSim:
    def __init__(self, *, progress=None, violations=None, events=None):
        self._progress = progress or {}
        self._violations = violations or []
        self._events = events or []

    @property
    def progress(self):
        return self._progress

    @property
    def violations(self):
        return self._violations

    @property
    def events(self):
        return self._events


# --- Helpers ---

def _minimal_run_result(**overrides) -> _RunResult:
    defaults = dict(
        success=True,
        agent_results=[
            _AgentResult("agent_a", 3, "completed", 2.5, trace=[
                _ToolCall(1, "acquire_lock", {"lock_id": "L1"},
                          {"status": "acquired"}, 0.01, time.time()),
                _ToolCall(1, "release_lock", {"lock_id": "L1"},
                          {"status": "released"}, 0.005, time.time()),
                _ToolCall(2, "signal_done", {}, {"status": "done"}, 0.001, time.time()),
            ]),
        ],
        duration=2.5,
        error=None,
    )
    defaults.update(overrides)
    return _RunResult(**defaults)


# --- Tests ---

def test_build_minimal():
    """Minimal build: no sim, no tracker, no monitor."""
    rr = _minimal_run_result()
    data = build_run_result_data(rr, task_id="3E", model="gpt-4.1-mini")

    assert data["meta"]["task_id"] == "3E"
    assert data["meta"]["model"] == "gpt-4.1-mini"
    assert data["result"]["success"] is True
    assert len(data["agents"]) == 1
    assert data["agents"][0]["agent_id"] == "agent_a"
    assert len(data["agents"][0]["trace"]) == 3
    # Optional sections absent
    assert "protocol_monitor" not in data
    assert "state_tracker" not in data
    assert "sim" not in data


def test_build_with_error():
    rr = _minimal_run_result(success=False, error="Timeout after 180s")
    data = build_run_result_data(rr, task_id="5M", model="gpt-4.1-mini")

    assert data["result"]["success"] is False
    assert data["result"]["error"] == "Timeout after 180s"


def test_build_with_monitor_trace():
    rr = _minimal_run_result()
    trace = [
        _TraceEntry("agent_a", "acquire", "L1"),
        _TraceEntry("agent_a", "send", "ch_ab", label="submit"),
    ]
    data = build_run_result_data(
        rr, task_id="3E", model="gpt-4.1-mini", monitor_trace=trace)

    assert "protocol_monitor" in data
    entries = data["protocol_monitor"]["trace"]
    assert len(entries) == 2
    assert entries[0]["operation"] == "acquire"
    assert "label" not in entries[0]  # no label for acquire
    assert entries[1]["label"] == "submit"


def test_build_with_state_tracker():
    rr = _minimal_run_result()
    violations = [
        _StateViolation(
            agent="agent_a",
            current_state="s1",
            operation="send",
            args={"channel": "ch", "label": "x"},
            valid_actions=[{"next_state": "s2", "receive": {"channel": "ch", "label": "y"}}],
            timestamp=time.time(),
        ),
    ]
    data = build_run_result_data(
        rr, task_id="3E", model="gpt-4.1-mini",
        tracker_states={"agent_a": "s3"},
        tracker_violations=violations,
    )

    assert "state_tracker" in data
    st = data["state_tracker"]
    assert st["final_states"]["agent_a"] == "s3"
    assert len(st["violations"]) == 1
    assert st["violations"][0]["operation"] == "send"


def test_build_with_sim():
    sim = _FakeSim(
        progress={"all_complete": False, "step_a": True},
        violations=[
            _Violation(1.0, "chef_a", "chop", "ordering", "chopped before washing"),
        ],
        events=[
            _SimEvent(1.0, "chef_a", "wash", {"item": "lettuce"}, True, {"ok": True}),
            _SimEvent(2.0, "chef_a", "chop", {"item": "lettuce"}, True,
                      {"ok": True},
                      violations=[
                          _Violation(2.0, "chef_a", "chop", "ordering",
                                     "chopped before washing"),
                      ]),
        ],
    )
    rr = _minimal_run_result()
    data = build_run_result_data(
        rr, task_id="12E", model="gpt-4.1-mini", sim=sim)

    assert "sim" in data
    assert data["sim"]["progress"]["all_complete"] is False
    assert len(data["sim"]["violations"]) == 1
    assert len(data["sim"]["events"]) == 2
    assert data["sim"]["events"][1]["violations"][0]["violation_type"] == "ordering"


def test_save_creates_file(tmp_path):
    rr = _minimal_run_result()
    output = tmp_path / "workspace" / "run_result.json"
    result_path = save_run_result(
        output, rr, task_id="3E", model="gpt-4.1-mini")

    assert result_path.exists()
    data = json.loads(result_path.read_text())
    assert data["meta"]["task_id"] == "3E"
    assert data["result"]["success"] is True


def test_json_roundtrip(tmp_path):
    """Ensure all values are JSON-serializable and survive a roundtrip."""
    sim = _FakeSim(
        progress={"done": True},
        violations=[_Violation(1.0, "a", "t", "v", "msg")],
        events=[_SimEvent(1.0, "a", "t", {"k": "v"}, True, {"r": 1})],
    )
    rr = _minimal_run_result()
    output = tmp_path / "run_result.json"
    save_run_result(
        output, rr,
        task_id="3E", model="gpt-4.1-mini",
        monitor_trace=[_TraceEntry("a", "send", "ch", "lbl")],
        tracker_states={"a": "s1"},
        tracker_violations=[
            _StateViolation("a", "s0", "send", {"channel": "ch"}, [], time.time()),
        ],
        sim=sim,
    )

    raw = output.read_text()
    data = json.loads(raw)
    # Re-serialize to ensure no non-serializable values
    json.dumps(data)

    assert "meta" in data
    assert "result" in data
    assert "agents" in data
    assert "protocol_monitor" in data
    assert "state_tracker" in data
    assert "sim" in data
