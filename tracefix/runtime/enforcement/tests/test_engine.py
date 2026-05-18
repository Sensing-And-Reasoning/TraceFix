"""Tests for runtime.engine — protocol execution."""

import pytest

from tracefix.runtime.enforcement.engine import run_ir, RunResult


# ---------------------------------------------------------------------------
# Deadlock detection
# ---------------------------------------------------------------------------

class TestDeadlock:
    def test_mutual_receive_deadlock(self):
        """Two agents each wait to receive before sending → deadlock."""
        ir = {
            "agents": [
                {"id": "a", "initial_state": "a1"},
                {"id": "b", "initial_state": "b1"},
            ],
            "resources": [],
            "channels": [
                {"id": "ch_ab", "from": "a", "to": "b"},
                {"id": "ch_ba", "from": "b", "to": "a"},
            ],
            "states": [
                {"id": "a1", "agent": "a", "actions": [
                    {"target": "a2", "receive": [{"channel": "ch_ba", "label": "msg"}]}
                ]},
                {"id": "a2", "agent": "a", "actions": [
                    {"target": "a_done", "send": [{"channel": "ch_ab", "label": "msg"}]}
                ]},
                {"id": "a_done", "agent": "a", "actions": []},
                {"id": "b1", "agent": "b", "actions": [
                    {"target": "b2", "receive": [{"channel": "ch_ab", "label": "msg"}]}
                ]},
                {"id": "b2", "agent": "b", "actions": [
                    {"target": "b_done", "send": [{"channel": "ch_ba", "label": "msg"}]}
                ]},
                {"id": "b_done", "agent": "b", "actions": []},
            ],
        }
        result = run_ir(ir, timeout=1)
        assert not result.success
        assert "Timeout" in result.error

    def test_lock_deadlock(self):
        """Two agents each hold a lock and wait for the other → deadlock."""
        ir = {
            "agents": [
                {"id": "a", "initial_state": "a1"},
                {"id": "b", "initial_state": "b1"},
            ],
            "resources": [
                {"id": "lockX", "type": "Lock"},
                {"id": "lockY", "type": "Lock"},
            ],
            "channels": [],
            "states": [
                # Agent a: acquire X, then try to acquire Y
                {"id": "a1", "agent": "a", "actions": [
                    {"target": "a2", "acquire": ["lockX"]}
                ]},
                {"id": "a2", "agent": "a", "actions": [
                    {"target": "a_done", "acquire": ["lockY"], "release": ["lockX"]}
                ]},
                {"id": "a_done", "agent": "a", "actions": []},
                # Agent b: acquire Y, then try to acquire X
                {"id": "b1", "agent": "b", "actions": [
                    {"target": "b2", "acquire": ["lockY"]}
                ]},
                {"id": "b2", "agent": "b", "actions": [
                    {"target": "b_done", "acquire": ["lockX"], "release": ["lockY"]}
                ]},
                {"id": "b_done", "agent": "b", "actions": []},
            ],
        }
        result = run_ir(ir, seed=42, timeout=1)
        assert not result.success
        assert "Timeout" in result.error
        assert "a" in result.final_states
        assert "b" in result.final_states


# ---------------------------------------------------------------------------
# Simple protocols
# ---------------------------------------------------------------------------

class TestSimpleLockProtocol:
    def test_two_agents_share_lock(self):
        """Two agents take turns with a lock — no deadlock."""
        ir = {
            "agents": [
                {"id": "a", "initial_state": "a1"},
                {"id": "b", "initial_state": "b1"},
            ],
            "resources": [{"id": "lock", "type": "Lock"}],
            "channels": [],
            "states": [
                {"id": "a1", "agent": "a", "actions": [
                    {"target": "a2", "acquire": ["lock"]}
                ]},
                {"id": "a2", "agent": "a", "actions": [
                    {"target": "a_done", "release": ["lock"]}
                ]},
                {"id": "a_done", "agent": "a", "actions": []},
                {"id": "b1", "agent": "b", "actions": [
                    {"target": "b2", "acquire": ["lock"]}
                ]},
                {"id": "b2", "agent": "b", "actions": [
                    {"target": "b_done", "release": ["lock"]}
                ]},
                {"id": "b_done", "agent": "b", "actions": []},
            ],
        }
        result = run_ir(ir, seed=42, timeout=5)
        assert result.success
        assert result.final_states == {"a": "a_done", "b": "b_done"}
        assert result.steps == 4  # a1→a2, a2→a_done, b1→b2, b2→b_done


class TestSimpleChannelProtocol:
    def test_ping_pong(self):
        """Agent a sends, agent b receives."""
        ir = {
            "agents": [
                {"id": "sender", "initial_state": "s1"},
                {"id": "receiver", "initial_state": "r1"},
            ],
            "resources": [],
            "channels": [{"id": "ch", "from": "sender", "to": "receiver"}],
            "states": [
                {"id": "s1", "agent": "sender", "actions": [
                    {"target": "s_done", "send": [{"channel": "ch", "label": "hello"}]}
                ]},
                {"id": "s_done", "agent": "sender", "actions": []},
                {"id": "r1", "agent": "receiver", "actions": [
                    {"target": "r_done", "receive": [{"channel": "ch", "label": "hello"}]}
                ]},
                {"id": "r_done", "agent": "receiver", "actions": []},
            ],
        }
        result = run_ir(ir, seed=42, timeout=5)
        assert result.success
        assert result.final_states == {"sender": "s_done", "receiver": "r_done"}
        assert result.steps == 2


class TestCounterProtocol:
    def test_counter_limits_iterations(self):
        """Agent loops, decrementing counter each time. Stops when counter exhausted."""
        ir = {
            "agents": [{"id": "worker", "initial_state": "w1"}],
            "resources": [{"id": "budget", "type": "Counter", "config": {"initial": 3}}],
            "channels": [],
            "states": [
                {"id": "w1", "agent": "worker", "actions": [
                    {"target": "w1", "acquire": ["budget"]},  # loop while budget > 0
                    {"target": "w_done"},                      # exit (always enabled)
                ]},
                {"id": "w_done", "agent": "worker", "actions": []},
            ],
        }
        # With random choice, some runs will loop more, some less
        results = [run_ir(ir, seed=s) for s in range(20)]
        assert all(r.success for r in results)
        # Step counts should vary (sometimes exit immediately, sometimes loop)
        step_counts = {r.steps for r in results}
        assert len(step_counts) > 1
