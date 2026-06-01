"""Tests for tracefix.runtime.enforcement.loader — loading states.json format."""

from pathlib import Path

import pytest

from tracefix.runtime.enforcement.loader import load_task, normalize_extracted_states
from tracefix.runtime.enforcement.engine import run_ir
from tracefix.runtime.enforcement.topology import build_topology

_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
_EXP_DIR = _ROOT / "workspace" / "claude46_exp2"

# These integration fixtures live in an experiment workspace that is NOT committed to
# the repo. When it's absent (fresh checkout / CI), the integration tests skip — matching
# the `test_all_33_tasks_*` guards below — instead of hard-failing on a missing fixture.
_REQUIRES_EXP = pytest.mark.skipif(
    not _EXP_DIR.exists(),
    reason=f"experiment workspace not present: {_EXP_DIR}")

# All 33 task IDs
_ALL_TASKS = [
    f"{n}{d}"
    for n in range(1, 12)
    for d in ("E", "M", "H")
]


# ---------------------------------------------------------------------------
# Integration: load real task dirs and run through engine
# ---------------------------------------------------------------------------

@_REQUIRES_EXP
class TestLoad3E:
    def test_load_and_run(self):
        ir = load_task(_EXP_DIR / "3E")
        result = run_ir(ir, seed=42, timeout=10)
        assert result.success, f"3E failed: {result.error}"
        assert result.steps > 0


@_REQUIRES_EXP
class TestLoad10H:
    def test_load_and_run(self):
        ir = load_task(_EXP_DIR / "10H")
        result = run_ir(ir, seed=42, timeout=10)
        assert result.success, f"10H failed: {result.error}"
        assert result.steps > 0
        # 10H has 7 agents
        assert len(ir["agents"]) == 7


# ---------------------------------------------------------------------------
# Unit tests: normalization
# ---------------------------------------------------------------------------

class TestNormalizeActionFields:
    def test_next_state_to_target(self):
        ir = {
            "agents": [{"id": "a"}],
            "resources": [],
            "channels": [],
        }
        extracted = {
            "initial_states": {"a": "s0"},
            "states": [{
                "id": "s0", "agent": "a",
                "actions": [{"next_state": "s1"}],
            }, {
                "id": "s1", "agent": "a",
                "actions": [],
            }],
        }
        result = normalize_extracted_states(ir, extracted)
        action = result["states"][0]["actions"][0]
        assert "target" in action
        assert "next_state" not in action
        assert action["target"] == "s1"

    def test_string_acquire_to_list(self):
        ir = {
            "agents": [{"id": "a"}],
            "resources": [{"id": "lk", "type": "Lock"}],
            "channels": [],
        }
        extracted = {
            "initial_states": {"a": "s0"},
            "states": [{
                "id": "s0", "agent": "a",
                "actions": [{"next_state": "s1", "acquire": "lk"}],
            }, {
                "id": "s1", "agent": "a",
                "actions": [],
            }],
        }
        result = normalize_extracted_states(ir, extracted)
        assert result["states"][0]["actions"][0]["acquire"] == ["lk"]

    def test_string_release_to_list(self):
        ir = {
            "agents": [{"id": "a"}],
            "resources": [{"id": "lk", "type": "Lock"}],
            "channels": [],
        }
        extracted = {
            "initial_states": {"a": "s0"},
            "states": [{
                "id": "s0", "agent": "a",
                "actions": [{"next_state": "s1", "release": "lk"}],
            }, {
                "id": "s1", "agent": "a",
                "actions": [],
            }],
        }
        result = normalize_extracted_states(ir, extracted)
        assert result["states"][0]["actions"][0]["release"] == ["lk"]

    def test_list_acquire_stays_list(self):
        ir = {
            "agents": [{"id": "a"}],
            "resources": [{"id": "lk", "type": "Lock"}],
            "channels": [],
        }
        extracted = {
            "initial_states": {"a": "s0"},
            "states": [{
                "id": "s0", "agent": "a",
                "actions": [{"next_state": "s1", "acquire": ["lk"]}],
            }, {
                "id": "s1", "agent": "a",
                "actions": [],
            }],
        }
        result = normalize_extracted_states(ir, extracted)
        assert result["states"][0]["actions"][0]["acquire"] == ["lk"]


class TestNormalizeDoneTerminal:
    def test_done_creates_terminal_state(self):
        ir = {
            "agents": [{"id": "a"}],
            "resources": [],
            "channels": [],
        }
        extracted = {
            "initial_states": {"a": "s0"},
            "states": [{
                "id": "s0", "agent": "a",
                "actions": [{"next_state": "__done__"}],
            }],
        }
        result = normalize_extracted_states(ir, extracted)
        state_ids = {s["id"] for s in result["states"]}
        assert "a__done__" in state_ids
        # The terminal state has empty actions
        terminal = next(s for s in result["states"] if s["id"] == "a__done__")
        assert terminal["actions"] == []
        assert terminal["agent"] == "a"

    def test_done_refs_rewritten(self):
        ir = {
            "agents": [{"id": "a"}],
            "resources": [],
            "channels": [],
        }
        extracted = {
            "initial_states": {"a": "s0"},
            "states": [{
                "id": "s0", "agent": "a",
                "actions": [{"next_state": "__done__"}],
            }],
        }
        result = normalize_extracted_states(ir, extracted)
        assert result["states"][0]["actions"][0]["target"] == "a__done__"

    def test_existing_terminal_not_duplicated(self):
        """If the extracted states already has an explicit terminal state, __done__ still works."""
        ir = {
            "agents": [{"id": "a"}, {"id": "b"}],
            "resources": [],
            "channels": [],
        }
        extracted = {
            "initial_states": {"a": "s0", "b": "b0"},
            "states": [
                {"id": "s0", "agent": "a", "actions": [{"next_state": "__done__"}]},
                {"id": "b0", "agent": "b", "actions": []},  # already terminal
            ],
        }
        result = normalize_extracted_states(ir, extracted)
        # a gets a__done__, b keeps b0
        state_ids = [s["id"] for s in result["states"]]
        assert "a__done__" in state_ids
        assert state_ids.count("a__done__") == 1


class TestNormalizeSendFormats:
    def test_single_object_to_list(self):
        ir = {
            "agents": [{"id": "a"}, {"id": "b"}],
            "resources": [],
            "channels": [{"id": "ch", "from": "a", "to": "b", "labels": ["msg"]}],
        }
        extracted = {
            "initial_states": {"a": "s0", "b": "b0"},
            "states": [
                {"id": "s0", "agent": "a", "actions": [
                    {"next_state": "s1", "send": {"channel": "ch", "label": "msg"}},
                ]},
                {"id": "s1", "agent": "a", "actions": []},
                {"id": "b0", "agent": "b", "actions": []},
            ],
        }
        result = normalize_extracted_states(ir, extracted)
        send = result["states"][0]["actions"][0]["send"]
        assert isinstance(send, list)
        assert len(send) == 1
        assert send[0]["channel"] == "ch"

    def test_array_stays_array(self):
        ir = {
            "agents": [{"id": "a"}, {"id": "b"}],
            "resources": [],
            "channels": [{"id": "ch", "from": "a", "to": "b", "labels": ["msg"]}],
        }
        extracted = {
            "initial_states": {"a": "s0", "b": "b0"},
            "states": [
                {"id": "s0", "agent": "a", "actions": [
                    {"next_state": "s1", "send": [{"channel": "ch", "label": "msg"}]},
                ]},
                {"id": "s1", "agent": "a", "actions": []},
                {"id": "b0", "agent": "b", "actions": []},
            ],
        }
        result = normalize_extracted_states(ir, extracted)
        send = result["states"][0]["actions"][0]["send"]
        assert isinstance(send, list)
        assert len(send) == 1


class TestNormalizeReceiveFormats:
    def test_single_object_to_list(self):
        ir = {
            "agents": [{"id": "a"}, {"id": "b"}],
            "resources": [],
            "channels": [{"id": "ch", "from": "b", "to": "a", "labels": ["msg"]}],
        }
        extracted = {
            "initial_states": {"a": "s0", "b": "b0"},
            "states": [
                {"id": "s0", "agent": "a", "actions": [
                    {"next_state": "s1", "receive": {"channel": "ch", "label": "msg"}},
                ]},
                {"id": "s1", "agent": "a", "actions": []},
                {"id": "b0", "agent": "b", "actions": []},
            ],
        }
        result = normalize_extracted_states(ir, extracted)
        recv = result["states"][0]["actions"][0]["receive"]
        assert isinstance(recv, list)
        assert len(recv) == 1
        assert recv[0]["channel"] == "ch"

    def test_array_stays_array(self):
        ir = {
            "agents": [{"id": "a"}, {"id": "b"}],
            "resources": [],
            "channels": [{"id": "ch", "from": "b", "to": "a", "labels": ["msg"]}],
        }
        extracted = {
            "initial_states": {"a": "s0", "b": "b0"},
            "states": [
                {"id": "s0", "agent": "a", "actions": [
                    {"next_state": "s1", "receive": [{"channel": "ch", "label": "msg"}]},
                ]},
                {"id": "s1", "agent": "a", "actions": []},
                {"id": "b0", "agent": "b", "actions": []},
            ],
        }
        result = normalize_extracted_states(ir, extracted)
        recv = result["states"][0]["actions"][0]["receive"]
        assert isinstance(recv, list)


class TestInitialStatesMerged:
    def test_initial_states_merged_into_agents(self):
        ir = {
            "agents": [{"id": "x"}, {"id": "y"}],
            "resources": [],
            "channels": [],
        }
        extracted = {
            "initial_states": {"x": "x_start", "y": "y_start"},
            "states": [
                {"id": "x_start", "agent": "x", "actions": []},
                {"id": "y_start", "agent": "y", "actions": []},
            ],
        }
        result = normalize_extracted_states(ir, extracted)
        agents = {a["id"]: a for a in result["agents"]}
        assert agents["x"]["initial_state"] == "x_start"
        assert agents["y"]["initial_state"] == "y_start"


# ---------------------------------------------------------------------------
# Guard / Increment / Local Variables
# ---------------------------------------------------------------------------

class TestGuardPassthrough:
    """Loader preserves guard/increment/local_variables fields."""

    def test_guard_and_increment_in_actions(self):
        ir = {
            "agents": [{"id": "a"}],
            "resources": [],
            "channels": [],
        }
        extracted = {
            "initial_states": {"a": "s0"},
            "local_variables": {"cnt": {"initial": 0, "agent": "a"}},
            "states": [
                {"id": "s0", "agent": "a", "actions": [
                    {"next_state": "s0", "guard": {"var": "cnt", "op": "<", "value": 2},
                     "increment": "cnt"},
                    {"next_state": "__done__"},
                ]},
            ],
        }
        result = normalize_extracted_states(ir, extracted)
        actions = result["states"][0]["actions"]
        assert actions[0]["guard"] == {"var": "cnt", "op": "<", "value": 2}
        assert actions[0]["increment"] == "cnt"
        assert "guard" not in actions[1]
        assert "increment" not in actions[1]

    def test_local_variables_passthrough(self):
        ir = {
            "agents": [{"id": "a"}],
            "resources": [],
            "channels": [],
        }
        extracted = {
            "initial_states": {"a": "s0"},
            "local_variables": {"cnt": {"initial": 0, "agent": "a"}},
            "states": [
                {"id": "s0", "agent": "a", "actions": []},
            ],
        }
        result = normalize_extracted_states(ir, extracted)
        assert "local_variables" in result
        assert result["local_variables"]["cnt"]["agent"] == "a"
        assert result["local_variables"]["cnt"]["initial"] == 0

    def test_no_local_variables_is_fine(self):
        ir = {
            "agents": [{"id": "a"}],
            "resources": [],
            "channels": [],
        }
        extracted = {
            "initial_states": {"a": "s0"},
            "states": [
                {"id": "s0", "agent": "a", "actions": []},
            ],
        }
        result = normalize_extracted_states(ir, extracted)
        assert "local_variables" not in result


class TestGuardPreventsExit:
    """Engine while-loop filtering: guard blocks premature exit."""

    def test_guard_prevents_premature_exit(self):
        """while(cnt < 2) loop must iterate exactly 2 times before exiting."""
        ir = {
            "agents": [{"id": "a", "initial_state": "loop"}],
            "resources": [],
            "channels": [],
            "local_variables": {"cnt": {"initial": 0, "agent": "a"}},
            "states": [
                {"id": "loop", "agent": "a", "actions": [
                    {"target": "loop", "guard": {"var": "cnt", "op": "<", "value": 2},
                     "increment": "cnt"},
                    {"target": "a__done__"},
                ]},
                {"id": "a__done__", "agent": "a", "actions": []},
            ],
        }
        result = run_ir(ir, seed=42, timeout=5)
        assert result.success
        # Should have exactly 3 steps: 2 loop iterations + 1 exit
        assert result.steps == 3
        assert result.final_states["a"] == "a__done__"

    def test_increment_updates_local_var(self):
        """Increment field advances counter, verified by needing 3 iterations."""
        ir = {
            "agents": [{"id": "a", "initial_state": "loop"}],
            "resources": [],
            "channels": [],
            "local_variables": {"x": {"initial": 0, "agent": "a"}},
            "states": [
                {"id": "loop", "agent": "a", "actions": [
                    {"target": "loop", "guard": {"var": "x", "op": "<", "value": 3},
                     "increment": "x"},
                    {"target": "a__done__"},
                ]},
                {"id": "a__done__", "agent": "a", "actions": []},
            ],
        }
        result = run_ir(ir, seed=42, timeout=5)
        assert result.success
        # 3 loop iterations + 1 exit = 4 steps
        assert result.steps == 4

    def test_guard_with_receive(self):
        """Guard + receive: loop body needs message; exit only when guard fails."""
        ir = {
            "agents": [{"id": "a", "initial_state": "a_loop"},
                       {"id": "b", "initial_state": "b0"}],
            "resources": [],
            "channels": [{"id": "ch", "from": "b", "to": "a", "labels": ["msg"]}],
            "local_variables": {"cnt": {"initial": 0, "agent": "a"}},
            "states": [
                # Agent a: loop receiving 2 messages
                {"id": "a_loop", "agent": "a", "actions": [
                    {"target": "a_loop",
                     "guard": {"var": "cnt", "op": "<", "value": 2},
                     "receive": [{"channel": "ch", "label": "msg"}],
                     "increment": "cnt"},
                    {"target": "a__done__"},
                ]},
                {"id": "a__done__", "agent": "a", "actions": []},
                # Agent b: send 2 messages then done
                {"id": "b0", "agent": "b", "actions": [
                    {"target": "b1", "send": [{"channel": "ch", "label": "msg"}]},
                ]},
                {"id": "b1", "agent": "b", "actions": [
                    {"target": "b__done__", "send": [{"channel": "ch", "label": "msg"}]},
                ]},
                {"id": "b__done__", "agent": "b", "actions": []},
            ],
        }
        result = run_ir(ir, seed=42, timeout=5)
        assert result.success
        assert result.final_states["a"] == "a__done__"
        assert result.final_states["b"] == "b__done__"


# ---------------------------------------------------------------------------
# Parametrized: all 33 tasks
# ---------------------------------------------------------------------------

# Tasks whose extracted protocols deadlock at runtime.
# 3H: EIC skip/wait-for-resub choice depends on earlier accept/revise decision (no guard).
# 6M: ci_run sends to dev_a/dev_b randomly — wrong choice causes deadlock (seed-dependent).
# 11M: worker loop count vs inspector pass_cnt capacity — cross-agent semantic coupling.
_DEADLOCK_TASKS = {"3H", "6M", "11M"}


@pytest.mark.parametrize("task_id", _ALL_TASKS)
def test_all_33_tasks_load(task_id):
    """Load every task dir, verify IR structure is valid for the engine."""
    task_dir = _EXP_DIR / task_id
    if not task_dir.exists():
        pytest.skip(f"Task dir {task_dir} not found")
    ir = load_task(task_dir)
    # Structural checks: loader produced valid engine-format IR
    assert "agents" in ir and "states" in ir
    assert all("initial_state" in a for a in ir["agents"])
    for state in ir["states"]:
        for action in state.get("actions", []):
            assert "target" in action, f"Missing 'target' in {state['id']}"
            assert "next_state" not in action, f"Residual 'next_state' in {state['id']}"
            for key in ("acquire", "release", "send", "receive"):
                if key in action:
                    assert isinstance(action[key], list), f"{key} not list in {state['id']}"


@pytest.mark.parametrize("task_id", _ALL_TASKS)
def test_all_33_tasks_run(task_id):
    """Load every task dir, run through engine, verify completion."""
    task_dir = _EXP_DIR / task_id
    if not task_dir.exists():
        pytest.skip(f"Task dir {task_dir} not found")
    if task_id in _DEADLOCK_TASKS:
        pytest.xfail(f"{task_id}: known protocol-level deadlock")
    ir = load_task(task_dir)
    result = run_ir(ir, seed=42, timeout=10)
    assert result.success, f"{task_id} failed: {result.error}"


# ---------------------------------------------------------------------------
# Topology compatibility
# ---------------------------------------------------------------------------

@_REQUIRES_EXP
class TestTopologyCompatible:
    def test_loaded_ir_works_with_topology(self):
        ir = load_task(_EXP_DIR / "3E")
        topo = build_topology(ir)
        assert topo.analysis.agent_count == 3
        assert topo.analysis.channel_count == 4


# A committed example workspace (engine-format: ir.json + states.json), so the
# enforcement load → run → topology path is exercised even on a fresh checkout
# without the (uncommitted) experiment workspace above.
_EXAMPLE = (_ROOT / "tracefix" / "runtime" / "sdk_adapter"
            / "examples" / "mas_doc_report")


@pytest.mark.skipif(not (_EXAMPLE / "states.json").exists(),
                    reason=f"example workspace not present: {_EXAMPLE}")
class TestLoadCommittedExample:
    def test_loads_and_runs_through_engine(self):
        ir = load_task(_EXAMPLE)
        result = run_ir(ir, seed=42, timeout=10)
        assert result.success, f"mas_doc_report failed: {result.error}"
        assert result.steps > 0
        assert len(ir["agents"]) == 3

    def test_topology_builds(self):
        ir = load_task(_EXAMPLE)
        topo = build_topology(ir)
        assert topo.analysis.agent_count == 3
        assert topo.analysis.channel_count > 0
