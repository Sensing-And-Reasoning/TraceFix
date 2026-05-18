"""Tests for StateTracker."""

import pytest

from tracefix.runtime.monitoring.state_tracker import StateTracker, StateViolation


# ---------------------------------------------------------------------------
# Fixtures — inline states_data dicts
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_linear():
    """1 agent, linear: s1 --[acquire lock1]--> s2 --[release lock1]--> s3_done."""
    return {
        "initial_states": {"agent1": "s1"},
        "states": [
            {"id": "s1", "agent": "agent1", "actions": [
                {"next_state": "s2", "acquire": "lock1"},
            ]},
            {"id": "s2", "agent": "agent1", "actions": [
                {"next_state": "s3_done", "release": "lock1"},
            ]},
            {"id": "s3_done", "agent": "agent1", "actions": []},
        ],
    }


@pytest.fixture
def with_channels():
    """2 agents with send/receive.
    A: a1 --[send ch, submit]--> a2_done.
    B: b1 --[receive ch]--> b2_done.
    """
    return {
        "initial_states": {"agentA": "a1", "agentB": "b1"},
        "states": [
            {"id": "a1", "agent": "agentA", "actions": [
                {"next_state": "a2_done", "send": {"channel": "ch", "label": "submit"}},
            ]},
            {"id": "a2_done", "agent": "agentA", "actions": []},
            {"id": "b1", "agent": "agentB", "actions": [
                {"next_state": "b2_done", "receive": {"channel": "ch"}},
            ]},
            {"id": "b2_done", "agent": "agentB", "actions": []},
        ],
    }


@pytest.fixture
def nondeterministic():
    """1 agent, nondeterministic: s1 --[send ch, accept]--> s2 OR --[send ch, reject]--> s3."""
    return {
        "initial_states": {"agent1": "s1"},
        "states": [
            {"id": "s1", "agent": "agent1", "actions": [
                {"next_state": "s2", "send": {"channel": "ch", "label": "accept"}},
                {"next_state": "s3", "send": {"channel": "ch", "label": "reject"}},
            ]},
            {"id": "s2", "agent": "agent1", "actions": []},
            {"id": "s3", "agent": "agent1", "actions": []},
        ],
    }


@pytest.fixture
def with_skip():
    """1 agent with skip state in the middle.
    s1 --[acquire lock]--> s2_skip(no ops) --> s3 --[release lock]--> s4_done.
    """
    return {
        "initial_states": {"agent1": "s1"},
        "states": [
            {"id": "s1", "agent": "agent1", "actions": [
                {"next_state": "s2_skip", "acquire": "lock1"},
            ]},
            {"id": "s2_skip", "agent": "agent1", "actions": [
                {"next_state": "s3"},  # skip — no coord ops
            ]},
            {"id": "s3", "agent": "agent1", "actions": [
                {"next_state": "s4_done", "release": "lock1"},
            ]},
            {"id": "s4_done", "agent": "agent1", "actions": []},
        ],
    }


@pytest.fixture
def compound_action():
    """1 agent with compound action (release + send in same action).
    s1 --[acquire lock]--> s2 --[release lock + send(ch, submit)]--> s3 --[receive(ch2)]--> s4_done.
    """
    return {
        "initial_states": {"agent1": "s1"},
        "states": [
            {"id": "s1", "agent": "agent1", "actions": [
                {"next_state": "s2", "acquire": "lock1"},
            ]},
            {"id": "s2", "agent": "agent1", "actions": [
                {"next_state": "s3", "release": "lock1",
                 "send": {"channel": "ch", "label": "submit"}},
            ]},
            {"id": "s3", "agent": "agent1", "actions": [
                {"next_state": "s4_done", "receive": {"channel": "ch2"}},
            ]},
            {"id": "s4_done", "agent": "agent1", "actions": []},
        ],
    }


@pytest.fixture
def initial_skip():
    """1 agent whose initial state is a skip.
    s0_skip(no ops) --> s1 --[acquire lock]--> s2_done.
    """
    return {
        "initial_states": {"agent1": "s0_skip"},
        "states": [
            {"id": "s0_skip", "agent": "agent1", "actions": [
                {"next_state": "s1"},  # skip
            ]},
            {"id": "s1", "agent": "agent1", "actions": [
                {"next_state": "s2_done", "acquire": "lock1"},
            ]},
            {"id": "s2_done", "agent": "agent1", "actions": []},
        ],
    }


@pytest.fixture
def nondeterministic_skip():
    """1 agent with nondeterministic skip state (like ed_collect in 3E).
    s0 --skip--> s1a --[receive chA]--> s2
    s0 --skip--> s1b --[receive chB]--> s2
    """
    return {
        "initial_states": {"agent1": "s0"},
        "states": [
            {"id": "s0", "agent": "agent1", "actions": [
                {"next_state": "s1a"},
                {"next_state": "s1b"},
            ]},
            {"id": "s1a", "agent": "agent1", "actions": [
                {"next_state": "s2_done", "receive": {"channel": "chA"}},
            ]},
            {"id": "s1b", "agent": "agent1", "actions": [
                {"next_state": "s2_done", "receive": {"channel": "chB"}},
            ]},
            {"id": "s2_done", "agent": "agent1", "actions": []},
        ],
    }


@pytest.fixture
def multi_send():
    """1 agent with action containing array of 2 sends.
    s1 --[send(chA, accept) + send(chB, accept)]--> s2_done.
    """
    return {
        "initial_states": {"agent1": "s1"},
        "states": [
            {"id": "s1", "agent": "agent1", "actions": [
                {"next_state": "s2_done", "send": [
                    {"channel": "chA", "label": "accept"},
                    {"channel": "chB", "label": "accept"},
                ]},
            ]},
            {"id": "s2_done", "agent": "agent1", "actions": []},
        ],
    }


@pytest.fixture
def ambiguous_skip_compound():
    """Nondeterministic skip where both targets share the same first op.
    Models 16M qa_test → qa_pass/qa_fail pattern:
    s0 --skip--> s1a --[release lock1 + send(ch, accept)]--> s2_done
    s0 --skip--> s1b --[release lock1 + send(ch, reject)]--> s3_done
    """
    return {
        "initial_states": {"agent1": "s0"},
        "states": [
            {"id": "s0", "agent": "agent1", "actions": [
                {"next_state": "s1a"},
                {"next_state": "s1b"},
            ]},
            {"id": "s1a", "agent": "agent1", "actions": [
                {"next_state": "s2_done", "release": "lock1",
                 "send": {"channel": "ch", "label": "accept"}},
            ]},
            {"id": "s1b", "agent": "agent1", "actions": [
                {"next_state": "s3_done", "release": "lock1",
                 "send": {"channel": "ch", "label": "reject"}},
            ]},
            {"id": "s2_done", "agent": "agent1", "actions": []},
            {"id": "s3_done", "agent": "agent1", "actions": []},
        ],
    }


@pytest.fixture
def ambiguous_skip_clean():
    """Nondeterministic skip where both targets have clean (single-op) matches.
    s0 --skip--> s1a --[send(ch, accept)]--> s2_done
    s0 --skip--> s1b --[send(ch, reject)]--> s3_done
    Both match on receive from upstream, but differ on send label.
    Actually, both have different send labels so they disambiguate at first op.
    Use release as the shared op instead:
    s0 --skip--> s1a --[release lock1]--> s2 --[send(ch, accept)]--> s3_done
    s0 --skip--> s1b --[release lock1]--> s4 --[send(ch, reject)]--> s5_done
    """
    return {
        "initial_states": {"agent1": "s0"},
        "states": [
            {"id": "s0", "agent": "agent1", "actions": [
                {"next_state": "s1a"},
                {"next_state": "s1b"},
            ]},
            {"id": "s1a", "agent": "agent1", "actions": [
                {"next_state": "s2", "release": "lock1"},
            ]},
            {"id": "s1b", "agent": "agent1", "actions": [
                {"next_state": "s4", "release": "lock1"},
            ]},
            {"id": "s2", "agent": "agent1", "actions": [
                {"next_state": "s3_done", "send": {"channel": "ch", "label": "accept"}},
            ]},
            {"id": "s3_done", "agent": "agent1", "actions": []},
            {"id": "s4", "agent": "agent1", "actions": [
                {"next_state": "s5_done", "send": {"channel": "ch", "label": "reject"}},
            ]},
            {"id": "s5_done", "agent": "agent1", "actions": []},
        ],
    }


@pytest.fixture
def receive_with_label():
    """1 agent, nondeterministic receive distinguished by label.
    s1 --[receive(ch, accept)]--> s2_done OR --[receive(ch, revise)]--> s3.
    """
    return {
        "initial_states": {"agent1": "s1"},
        "states": [
            {"id": "s1", "agent": "agent1", "actions": [
                {"next_state": "s2_done", "receive": {"channel": "ch", "label": "accept"}},
                {"next_state": "s3", "receive": {"channel": "ch", "label": "revise"}},
            ]},
            {"id": "s3", "agent": "agent1", "actions": []},
        ],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_happy_path_linear(self, simple_linear):
        tracker = StateTracker(simple_linear)
        assert tracker.current_states == {"agent1": "s1"}

        assert tracker.on_acquire("agent1", "lock1") is True
        assert tracker.current_states["agent1"] == "s2"

        assert tracker.on_release("agent1", "lock1") is True
        assert tracker.current_states["agent1"] == "s3_done"

        assert tracker.violation_count == 0

    def test_channel_send_receive(self, with_channels):
        tracker = StateTracker(with_channels)

        assert tracker.on_send("agentA", "ch", "submit") is True
        assert tracker.current_states["agentA"] == "a2_done"

        assert tracker.on_receive("agentB", "ch") is True
        assert tracker.current_states["agentB"] == "b2_done"

        assert tracker.violation_count == 0


class TestViolations:
    def test_violation_wrong_op(self, simple_linear):
        """Agent in state expecting acquire, call on_send → violation."""
        tracker = StateTracker(simple_linear)
        assert tracker.on_send("agent1", "ch", "hello") is False
        assert tracker.violation_count == 1

        v = tracker.violations[0]
        assert v.agent == "agent1"
        assert v.current_state == "s1"
        assert v.operation == "send"
        # State unchanged after violation
        assert tracker.current_states["agent1"] == "s1"

    def test_terminal_state_violation(self, simple_linear):
        """Agent in done state, any op → violation."""
        tracker = StateTracker(simple_linear)
        tracker.on_acquire("agent1", "lock1")
        tracker.on_release("agent1", "lock1")
        assert tracker.current_states["agent1"] == "s3_done"

        assert tracker.on_acquire("agent1", "lock1") is False
        assert tracker.violation_count == 1

    def test_wrong_resource(self, simple_linear):
        """Acquiring wrong resource → violation."""
        tracker = StateTracker(simple_linear)
        assert tracker.on_acquire("agent1", "wrong_lock") is False
        assert tracker.violation_count == 1


class TestNondeterministic:
    def test_nondeterministic_accept(self, nondeterministic):
        tracker = StateTracker(nondeterministic)
        assert tracker.on_send("agent1", "ch", "accept") is True
        assert tracker.current_states["agent1"] == "s2"
        assert tracker.violation_count == 0

    def test_nondeterministic_reject(self, nondeterministic):
        tracker = StateTracker(nondeterministic)
        assert tracker.on_send("agent1", "ch", "reject") is True
        assert tracker.current_states["agent1"] == "s3"
        assert tracker.violation_count == 0


class TestSkipStates:
    def test_skip_state_auto_advance(self, with_skip):
        """After matching, agent skips over internal skip state."""
        tracker = StateTracker(with_skip)

        assert tracker.on_acquire("agent1", "lock1") is True
        # Should auto-advance past s2_skip to s3
        assert tracker.current_states["agent1"] == "s3"

        assert tracker.on_release("agent1", "lock1") is True
        assert tracker.current_states["agent1"] == "s4_done"
        assert tracker.violation_count == 0

    def test_initial_skip_advance(self, initial_skip):
        """Initial state is a skip → auto-advanced at construction time."""
        tracker = StateTracker(initial_skip)
        # Should have advanced past s0_skip to s1
        assert tracker.current_states["agent1"] == "s1"

        assert tracker.on_acquire("agent1", "lock1") is True
        assert tracker.current_states["agent1"] == "s2_done"
        assert tracker.violation_count == 0

    def test_skip_state_nondeterministic_stop(self, nondeterministic_skip):
        """Nondeterministic skip state: don't auto-advance, resolve on first op."""
        tracker = StateTracker(nondeterministic_skip)
        # Should NOT auto-advance (2 skip actions)
        assert tracker.current_states["agent1"] == "s0"

    def test_nondeterministic_skip_resolved_by_op(self, nondeterministic_skip):
        """Nondeterministic skip resolved by looking through to matching branch."""
        tracker = StateTracker(nondeterministic_skip)

        # Receive on chA → should resolve through s0 skip to s1a, then match
        assert tracker.on_receive("agent1", "chA") is True
        assert tracker.current_states["agent1"] == "s2_done"
        assert tracker.violation_count == 0

    def test_nondeterministic_skip_other_branch(self, nondeterministic_skip):
        """Nondeterministic skip resolved via the other branch."""
        tracker = StateTracker(nondeterministic_skip)

        assert tracker.on_receive("agent1", "chB") is True
        assert tracker.current_states["agent1"] == "s2_done"
        assert tracker.violation_count == 0


class TestCompoundActions:
    def test_compound_action(self, compound_action):
        """release + send in same action → both ops consumed, single transition."""
        tracker = StateTracker(compound_action)

        # Acquire to reach s2
        assert tracker.on_acquire("agent1", "lock1") is True
        assert tracker.current_states["agent1"] == "s2"

        # First op of compound: release
        assert tracker.on_release("agent1", "lock1") is True
        # Should NOT have transitioned yet (pending send)
        assert tracker.current_states["agent1"] == "s2"

        # Second op of compound: send
        assert tracker.on_send("agent1", "ch", "submit") is True
        # NOW should transition to s3
        assert tracker.current_states["agent1"] == "s3"

        assert tracker.violation_count == 0

    def test_compound_action_reverse_order(self, compound_action):
        """Compound action ops can arrive in any order."""
        tracker = StateTracker(compound_action)
        tracker.on_acquire("agent1", "lock1")

        # Send first, then release (opposite order from action definition)
        assert tracker.on_send("agent1", "ch", "submit") is True
        assert tracker.current_states["agent1"] == "s2"  # still pending

        assert tracker.on_release("agent1", "lock1") is True
        assert tracker.current_states["agent1"] == "s3"  # now transitioned
        assert tracker.violation_count == 0

    def test_compound_wrong_pending_op(self, compound_action):
        """Wrong op while pending → violation."""
        tracker = StateTracker(compound_action)
        tracker.on_acquire("agent1", "lock1")

        # Start compound with release
        tracker.on_release("agent1", "lock1")
        # Wrong op: acquire instead of expected send
        assert tracker.on_acquire("agent1", "lock1") is False
        assert tracker.violation_count == 1

    def test_multi_send_action(self, multi_send):
        """Action with send array (2 sends) → both consumed before transition."""
        tracker = StateTracker(multi_send)

        # First send
        assert tracker.on_send("agent1", "chA", "accept") is True
        assert tracker.current_states["agent1"] == "s1"  # pending

        # Second send
        assert tracker.on_send("agent1", "chB", "accept") is True
        assert tracker.current_states["agent1"] == "s2_done"  # transitioned
        assert tracker.violation_count == 0


class TestReceiveWithLabel:
    def test_receive_accept_label(self, receive_with_label):
        tracker = StateTracker(receive_with_label)
        assert tracker.on_receive("agent1", "ch", "accept") is True
        assert tracker.current_states["agent1"] == "s2_done"
        assert tracker.violation_count == 0

    def test_receive_revise_label(self, receive_with_label):
        tracker = StateTracker(receive_with_label)
        assert tracker.on_receive("agent1", "ch", "revise") is True
        assert tracker.current_states["agent1"] == "s3"
        assert tracker.violation_count == 0

    def test_receive_wrong_label(self, receive_with_label):
        """Receive with label that doesn't match any action → violation."""
        tracker = StateTracker(receive_with_label)
        assert tracker.on_receive("agent1", "ch", "unknown") is False
        assert tracker.violation_count == 1

    def test_receive_no_label_matches_any(self, receive_with_label):
        """Receive without label matches first action with that channel."""
        tracker = StateTracker(receive_with_label)
        assert tracker.on_receive("agent1", "ch") is True
        assert tracker.violation_count == 0


class TestAmbiguousSkipPaths:
    """Tests for NFA-style candidate tracking when skip paths share first op."""

    def test_ambiguous_compound_accept_path(self, ambiguous_skip_compound):
        """release lock1 then send accept → resolves to s1a path → s2_done."""
        tracker = StateTracker(ambiguous_skip_compound)
        assert tracker.current_states["agent1"] == "s0"

        # First op: release lock1 — ambiguous (both s1a and s1b match)
        assert tracker.on_release("agent1", "lock1") is True
        # State should still be s0 (deferred, tracking candidates)
        assert tracker.current_states["agent1"] == "s0"

        # Second op: send accept — disambiguates to s1a path
        assert tracker.on_send("agent1", "ch", "accept") is True
        assert tracker.current_states["agent1"] == "s2_done"
        assert tracker.violation_count == 0

    def test_ambiguous_compound_reject_path(self, ambiguous_skip_compound):
        """release lock1 then send reject → resolves to s1b path → s3_done."""
        tracker = StateTracker(ambiguous_skip_compound)

        assert tracker.on_release("agent1", "lock1") is True
        assert tracker.current_states["agent1"] == "s0"  # deferred

        assert tracker.on_send("agent1", "ch", "reject") is True
        assert tracker.current_states["agent1"] == "s3_done"
        assert tracker.violation_count == 0

    def test_ambiguous_compound_wrong_second_op(self, ambiguous_skip_compound):
        """release lock1 then wrong op → violation."""
        tracker = StateTracker(ambiguous_skip_compound)

        assert tracker.on_release("agent1", "lock1") is True
        # Wrong second op — neither accept nor reject
        assert tracker.on_acquire("agent1", "lock1") is False
        assert tracker.violation_count == 1

    def test_ambiguous_clean_accept_path(self, ambiguous_skip_clean):
        """Clean skip targets: release lock1 then send accept → s3_done."""
        tracker = StateTracker(ambiguous_skip_clean)
        assert tracker.current_states["agent1"] == "s0"

        # First op: release lock1 — both s1a and s1b match (clean, no remaining)
        assert tracker.on_release("agent1", "lock1") is True

        # Second op: send accept — disambiguates to s1a → s2 path
        assert tracker.on_send("agent1", "ch", "accept") is True
        assert tracker.current_states["agent1"] == "s3_done"
        assert tracker.violation_count == 0

    def test_ambiguous_clean_reject_path(self, ambiguous_skip_clean):
        """Clean skip targets: release lock1 then send reject → s5_done."""
        tracker = StateTracker(ambiguous_skip_clean)

        assert tracker.on_release("agent1", "lock1") is True

        assert tracker.on_send("agent1", "ch", "reject") is True
        assert tracker.current_states["agent1"] == "s5_done"
        assert tracker.violation_count == 0


class TestSkipChainCycleDetection:
    def test_auto_advance_cycle(self):
        """Skip-chain cycle in initial state → stops, doesn't hang."""
        data = {
            "initial_states": {"agent1": "s1"},
            "states": [
                {"id": "s1", "agent": "agent1", "actions": [
                    {"next_state": "s2"},  # skip
                ]},
                {"id": "s2", "agent": "agent1", "actions": [
                    {"next_state": "s1"},  # skip → cycle back to s1
                ]},
            ],
        }
        # Should not hang — cycle detection breaks the loop
        tracker = StateTracker(data)
        assert tracker.current_states["agent1"] in ("s1", "s2")

    def test_auto_advance_cycle_logs_error(self, caplog):
        """Skip-chain cycle emits ERROR (not WARNING) indicating malformed states.json."""
        import logging
        data = {
            "initial_states": {"agent1": "s1"},
            "states": [
                {"id": "s1", "agent": "agent1", "actions": [
                    {"next_state": "s2"},
                ]},
                {"id": "s2", "agent": "agent1", "actions": [
                    {"next_state": "s1"},
                ]},
            ],
        }
        with caplog.at_level(logging.ERROR, logger="tracefix.runtime.monitoring.state_tracker"):
            StateTracker(data)
        assert any("skip-chain cycle" in r.message.lower() and r.levelno == logging.ERROR
                    for r in caplog.records)

    def test_resolve_skip_chain_cycle(self):
        """Skip-chain cycle in nondeterministic resolution → stops, doesn't hang."""
        data = {
            "initial_states": {"agent1": "s0"},
            "states": [
                {"id": "s0", "agent": "agent1", "actions": [
                    {"next_state": "s1"},  # skip → into cycle
                    {"next_state": "s3", "acquire": "lock1"},  # normal
                ]},
                {"id": "s1", "agent": "agent1", "actions": [
                    {"next_state": "s2"},  # skip
                ]},
                {"id": "s2", "agent": "agent1", "actions": [
                    {"next_state": "s1"},  # skip → cycle
                ]},
                {"id": "s3", "agent": "agent1", "actions": []},
            ],
        }
        tracker = StateTracker(data)
        # Should still be able to match the non-cycle branch
        assert tracker.on_acquire("agent1", "lock1") is True
        assert tracker.current_states["agent1"] == "s3"

    def test_resolve_skip_chain_cycle_logs_error(self, caplog):
        """_resolve_skip_chain cycle emits ERROR for malformed states.json."""
        import logging
        data = {
            "initial_states": {"agent1": "s0"},
            "states": [
                # s0 has ONLY skip actions so step 2b (_resolve_skip_chain) is used
                {"id": "s0", "agent": "agent1", "actions": [
                    {"next_state": "s1"},   # skip → cycle (s1→s2→s1)
                    {"next_state": "s4"},   # skip → valid match
                ]},
                {"id": "s1", "agent": "agent1", "actions": [
                    {"next_state": "s2"},
                ]},
                {"id": "s2", "agent": "agent1", "actions": [
                    {"next_state": "s1"},   # cycle back
                ]},
                {"id": "s4", "agent": "agent1", "actions": [
                    {"next_state": "s5", "acquire": "lock1"},
                ]},
                {"id": "s5", "agent": "agent1", "actions": []},
            ],
        }
        tracker = StateTracker(data)
        with caplog.at_level(logging.ERROR, logger="tracefix.runtime.monitoring.state_tracker"):
            tracker.on_acquire("agent1", "lock1")
        assert any("skip-chain cycle" in r.message.lower() and r.levelno == logging.ERROR
                    for r in caplog.records)


class TestEdgeCases:
    def test_unknown_agent(self, simple_linear):
        """on_acquire for unknown agent → no crash, returns False."""
        tracker = StateTracker(simple_linear)
        assert tracker.on_acquire("unknown", "lock1") is False
        # No violation recorded for unknown agents
        assert tracker.violation_count == 0

    def test_empty_states(self):
        """Empty states_data → no crash."""
        tracker = StateTracker({"initial_states": {}, "states": []})
        assert tracker.current_states == {}
        assert tracker.violation_count == 0

    def test_resource_as_list(self):
        """acquire/release specified as list in states.json."""
        data = {
            "initial_states": {"a": "s1"},
            "states": [
                {"id": "s1", "agent": "a", "actions": [
                    {"next_state": "s2", "acquire": ["lock1", "lock2"]},
                ]},
                {"id": "s2", "agent": "a", "actions": []},
            ],
        }
        tracker = StateTracker(data)
        # Acquiring lock1 matches (it's in the list)
        assert tracker.on_acquire("a", "lock1") is True
        # lock2 still pending
        assert tracker.current_states["a"] == "s1"
        assert tracker.on_acquire("a", "lock2") is True
        assert tracker.current_states["a"] == "s2"
        assert tracker.violation_count == 0


# ---------------------------------------------------------------------------
# Guard & Counter Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def with_guard_loop():
    """Models the 6H REVIEWER pattern: while(count < 3) loop with asymmetric increment.

    rv_loop:
      guard(count < 3) → rv_wait (enter loop)
      (no guard)       → rv_done (exit loop)

    rv_wait --[receive ch]--> rv_decide

    rv_decide:
      --[send(ch_out, approved) + increment count]--> rv_loop
      --[send(ch_out, revise)]--> rv_loop   (NO increment)
    """
    return {
        "initial_states": {"REVIEWER": "rv_loop"},
        "states": [
            {"id": "rv_loop", "agent": "REVIEWER", "actions": [
                {"next_state": "rv_wait",
                 "guard": {"var": "rvCount", "op": "<", "value": 3}},
                {"next_state": "rv_done"},
            ]},
            {"id": "rv_wait", "agent": "REVIEWER", "actions": [
                {"next_state": "rv_decide",
                 "receive": {"channel": "ch_in"}},
            ]},
            {"id": "rv_decide", "agent": "REVIEWER", "actions": [
                {"next_state": "rv_loop",
                 "send": {"channel": "ch_out", "label": "approved"},
                 "increment": "rvCount"},
                {"next_state": "rv_loop",
                 "send": {"channel": "ch_out", "label": "revise"}},
            ]},
            {"id": "rv_done", "agent": "REVIEWER", "actions": []},
        ],
    }


@pytest.fixture
def with_guard_loop_local_vars():
    """Same as with_guard_loop but with explicit local_variables."""
    return {
        "initial_states": {"REVIEWER": "rv_loop"},
        "local_variables": {
            "rvCount": {"initial": 0, "agent": "REVIEWER"},
        },
        "states": [
            {"id": "rv_loop", "agent": "REVIEWER", "actions": [
                {"next_state": "rv_wait",
                 "guard": {"var": "rvCount", "op": "<", "value": 3}},
                {"next_state": "rv_done"},
            ]},
            {"id": "rv_wait", "agent": "REVIEWER", "actions": [
                {"next_state": "rv_decide",
                 "receive": {"channel": "ch_in"}},
            ]},
            {"id": "rv_decide", "agent": "REVIEWER", "actions": [
                {"next_state": "rv_loop",
                 "send": {"channel": "ch_out", "label": "approved"},
                 "increment": "rvCount"},
                {"next_state": "rv_loop",
                 "send": {"channel": "ch_out", "label": "revise"}},
            ]},
            {"id": "rv_done", "agent": "REVIEWER", "actions": []},
        ],
    }


@pytest.fixture
def with_list_increment():
    """Action with list-format increment (multiple counters)."""
    return {
        "initial_states": {"agent1": "s1"},
        "states": [
            {"id": "s1", "agent": "agent1", "actions": [
                {"next_state": "s1",
                 "send": {"channel": "ch", "label": "ok"},
                 "guard": {"var": "countA", "op": "<", "value": 2},
                 "increment": ["countA", "countB"]},
                {"next_state": "s2_done"},
            ]},
            {"id": "s2_done", "agent": "agent1", "actions": []},
        ],
    }


# ---------------------------------------------------------------------------
# Guard & Counter Tests
# ---------------------------------------------------------------------------

class TestGuardFilteringAndCounters:
    """Tests for counter-based guard filtering and increment tracking."""

    def test_guard_loop_initial_state_auto_advances_into_loop(self, with_guard_loop):
        """Guard < 3 with count=0 → enters loop, auto-advances to rv_wait."""
        tracker = StateTracker(with_guard_loop)
        # Should auto-advance: rv_loop (guard true → rv_wait is skip target? No, rv_wait has receive)
        # Actually rv_loop guard=true → rv_wait (single filtered action, but rv_wait has receive, not skip)
        # rv_loop has 2 actions; after filtering, only guarded one (count<3 true) → 1 action
        # That action is a skip (no coord ops) → auto-advance to rv_wait
        assert tracker.current_states["REVIEWER"] == "rv_wait"

    def test_guard_loop_receive_then_approved_increments(self, with_guard_loop):
        """receive → send approved → rvCount increments, loops back."""
        tracker = StateTracker(with_guard_loop)
        assert tracker.counter_values["rvCount"] == 0

        # Receive a review request
        assert tracker.on_receive("REVIEWER", "ch_in") is True
        assert tracker.current_states["REVIEWER"] == "rv_decide"

        # Approve — should increment rvCount
        assert tracker.on_send("REVIEWER", "ch_out", "approved") is True
        assert tracker.counter_values["rvCount"] == 1
        # Should loop back to rv_loop and auto-advance to rv_wait (guard still true: 1 < 3)
        assert tracker.current_states["REVIEWER"] == "rv_wait"

    def test_guard_loop_receive_then_revise_no_increment(self, with_guard_loop):
        """receive → send revise → rvCount does NOT increment, loops back."""
        tracker = StateTracker(with_guard_loop)

        assert tracker.on_receive("REVIEWER", "ch_in") is True
        assert tracker.on_send("REVIEWER", "ch_out", "revise") is True
        assert tracker.counter_values["rvCount"] == 0  # NOT incremented
        assert tracker.current_states["REVIEWER"] == "rv_wait"

    def test_guard_loop_exits_after_3_approvals(self, with_guard_loop):
        """After 3 approved sends, guard becomes false, agent reaches rv_done."""
        tracker = StateTracker(with_guard_loop)

        for i in range(3):
            assert tracker.on_receive("REVIEWER", "ch_in") is True
            assert tracker.on_send("REVIEWER", "ch_out", "approved") is True

        assert tracker.counter_values["rvCount"] == 3
        # Guard 3 < 3 is false → exit branch → rv_done
        assert tracker.current_states["REVIEWER"] == "rv_done"
        assert tracker.violation_count == 0

    def test_guard_loop_mixed_revise_approved(self, with_guard_loop):
        """1 revise + 3 approved = 4 total reviews but loop exits correctly."""
        tracker = StateTracker(with_guard_loop)

        # Review 1: revise (no increment)
        tracker.on_receive("REVIEWER", "ch_in")
        tracker.on_send("REVIEWER", "ch_out", "revise")
        assert tracker.counter_values["rvCount"] == 0

        # Review 2: approved (increment to 1)
        tracker.on_receive("REVIEWER", "ch_in")
        tracker.on_send("REVIEWER", "ch_out", "approved")
        assert tracker.counter_values["rvCount"] == 1

        # Review 3: approved (increment to 2)
        tracker.on_receive("REVIEWER", "ch_in")
        tracker.on_send("REVIEWER", "ch_out", "approved")
        assert tracker.counter_values["rvCount"] == 2

        # Still in loop (2 < 3)
        assert tracker.current_states["REVIEWER"] == "rv_wait"

        # Review 4: approved (increment to 3)
        tracker.on_receive("REVIEWER", "ch_in")
        tracker.on_send("REVIEWER", "ch_out", "approved")
        assert tracker.counter_values["rvCount"] == 3

        # Now exits: 3 < 3 is false → rv_done
        assert tracker.current_states["REVIEWER"] == "rv_done"
        assert tracker.violation_count == 0

    def test_can_terminate_blocked_by_guard(self, with_guard_loop):
        """can_terminate returns False when guard prevents reaching terminal."""
        tracker = StateTracker(with_guard_loop)
        # rvCount=0, guard 0<3 is true → only loop body enabled → can't reach done
        assert tracker.can_terminate("REVIEWER") is False

    def test_can_terminate_allowed_after_completion(self, with_guard_loop):
        """can_terminate returns True after all increments are done."""
        tracker = StateTracker(with_guard_loop)

        for _ in range(3):
            tracker.on_receive("REVIEWER", "ch_in")
            tracker.on_send("REVIEWER", "ch_out", "approved")

        # Now at rv_done (terminal)
        assert tracker.can_terminate("REVIEWER") is True

    def test_can_terminate_unknown_agent(self, with_guard_loop):
        """can_terminate returns True for unknown agents (don't block)."""
        tracker = StateTracker(with_guard_loop)
        assert tracker.can_terminate("UNKNOWN") is True

    def test_counter_discovery_from_actions(self, with_guard_loop):
        """Counters are discovered from guard/increment fields when no local_variables."""
        tracker = StateTracker(with_guard_loop)
        assert "rvCount" in tracker.counter_values
        assert tracker.counter_values["rvCount"] == 0

    def test_counter_init_from_local_variables(self, with_guard_loop_local_vars):
        """Counters initialized from local_variables when present."""
        tracker = StateTracker(with_guard_loop_local_vars)
        assert "rvCount" in tracker.counter_values
        assert tracker.counter_values["rvCount"] == 0

    def test_list_format_increment(self, with_list_increment):
        """increment as list increments multiple counters."""
        tracker = StateTracker(with_list_increment)
        assert tracker.counter_values == {"countA": 0, "countB": 0}

        assert tracker.on_send("agent1", "ch", "ok") is True
        assert tracker.counter_values == {"countA": 1, "countB": 1}

        assert tracker.on_send("agent1", "ch", "ok") is True
        assert tracker.counter_values == {"countA": 2, "countB": 2}

        # Guard 2 < 2 is false → exit to s2_done
        assert tracker.current_states["agent1"] == "s2_done"
        assert tracker.violation_count == 0


class TestGuardOperators:
    """Test all guard comparison operators."""

    def _make_states(self, op, value, initial=0):
        data = {
            "initial_states": {"a": "s1"},
            "states": [
                {"id": "s1", "agent": "a", "actions": [
                    {"next_state": "s2",
                     "guard": {"var": "x", "op": op, "value": value}},
                    {"next_state": "s3_done"},
                ]},
                {"id": "s2", "agent": "a", "actions": [
                    {"next_state": "s1", "increment": "x"},
                ]},
                {"id": "s3_done", "agent": "a", "actions": []},
            ],
        }
        if initial != 0:
            data["local_variables"] = {"x": {"initial": initial, "agent": "a"}}
        return data

    def test_less_than(self):
        # Direct guard evaluation (auto-advance cycle detection prevents full loop unrolling)
        assert StateTracker._evaluate_guard({"var": "x", "op": "<", "value": 2}, {"x": 0}) is True
        assert StateTracker._evaluate_guard({"var": "x", "op": "<", "value": 2}, {"x": 1}) is True
        assert StateTracker._evaluate_guard({"var": "x", "op": "<", "value": 2}, {"x": 2}) is False

    def test_less_equal(self):
        assert StateTracker._evaluate_guard({"var": "x", "op": "<=", "value": 1}, {"x": 0}) is True
        assert StateTracker._evaluate_guard({"var": "x", "op": "<=", "value": 1}, {"x": 1}) is True
        assert StateTracker._evaluate_guard({"var": "x", "op": "<=", "value": 1}, {"x": 2}) is False

    def test_greater_than(self):
        tracker = StateTracker(self._make_states(">", 0, initial=2))
        # x=2: 2>0 true → s2 → inc → s1; x=3: 3>0 true → ... this loops forever
        # Better test: >1 with initial=2 → x=2: 2>1 true → inc → x=3: 3>1 true → infinite
        # Actually let's use != instead. For >, test guard evaluation directly.
        assert StateTracker._evaluate_guard({"var": "x", "op": ">", "value": 0}, {"x": 1}) is True
        assert StateTracker._evaluate_guard({"var": "x", "op": ">", "value": 0}, {"x": 0}) is False

    def test_greater_equal(self):
        assert StateTracker._evaluate_guard({"var": "x", "op": ">=", "value": 3}, {"x": 3}) is True
        assert StateTracker._evaluate_guard({"var": "x", "op": ">=", "value": 3}, {"x": 2}) is False

    def test_equal(self):
        assert StateTracker._evaluate_guard({"var": "x", "op": "=", "value": 5}, {"x": 5}) is True
        assert StateTracker._evaluate_guard({"var": "x", "op": "=", "value": 5}, {"x": 4}) is False
        assert StateTracker._evaluate_guard({"var": "x", "op": "==", "value": 5}, {"x": 5}) is True

    def test_not_equal(self):
        assert StateTracker._evaluate_guard({"var": "x", "op": "!=", "value": 0}, {"x": 1}) is True
        assert StateTracker._evaluate_guard({"var": "x", "op": "!=", "value": 0}, {"x": 0}) is False
        assert StateTracker._evaluate_guard({"var": "x", "op": "#", "value": 0}, {"x": 1}) is True


class TestExistingBehaviorUnchanged:
    """Verify counter tracking is a no-op when no guards/increments present."""

    def test_no_counters_in_simple_linear(self, simple_linear):
        tracker = StateTracker(simple_linear)
        assert tracker.counter_values == {}
        assert tracker.can_terminate("agent1") is False  # has coord ops ahead, not terminal

    def test_no_counters_in_channel_fixture(self, with_channels):
        tracker = StateTracker(with_channels)
        assert tracker.counter_values == {}

    def test_can_terminate_at_done_state(self, simple_linear):
        tracker = StateTracker(simple_linear)
        tracker.on_acquire("agent1", "lock1")
        tracker.on_release("agent1", "lock1")
        assert tracker.current_states["agent1"] == "s3_done"
        assert tracker.can_terminate("agent1") is True
