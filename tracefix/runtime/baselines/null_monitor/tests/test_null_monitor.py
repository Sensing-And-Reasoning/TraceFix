"""Tests for tracefix.runtime.baselines.null_monitor NullMonitor — relaxed topology validation."""

import pytest

from tracefix.runtime.monitoring.monitor import ProtocolViolation
from tracefix.runtime.baselines.null_monitor.null_monitor import NullMonitor


# ---------------------------------------------------------------------------
# Fixture IR
# ---------------------------------------------------------------------------

SIMPLE_IR = {
    "agents": [
        {"id": "agent_a"},
        {"id": "agent_b"},
    ],
    "resources": [
        {"id": "lock_1", "type": "Lock"},
        {"id": "counter_1", "type": "Counter", "initial_value": 3},
    ],
    "channels": [
        {"id": "ch_ab", "from": "agent_a", "to": "agent_b", "labels": ["request", "data"]},
        {"id": "ch_ba", "from": "agent_b", "to": "agent_a", "labels": ["response"]},
    ],
}

NO_LABELS_IR = {
    "agents": [{"id": "x"}, {"id": "y"}],
    "resources": [],
    "channels": [
        {"id": "ch_xy", "from": "x", "to": "y"},
    ],
}


@pytest.fixture
def monitor():
    return NullMonitor(SIMPLE_IR)


# ---------------------------------------------------------------------------
# Valid operations
# ---------------------------------------------------------------------------

class TestValidOperations:
    def test_valid_send(self, monitor):
        result = monitor.validate_send("agent_a", "ch_ab", label="request")
        assert result is True

    def test_valid_send_any_agent(self, monitor):
        """NullMonitor does NOT check topology — any agent can send on any channel."""
        result = monitor.validate_send("agent_b", "ch_ab", label="data")
        assert result is True

    def test_valid_receive(self, monitor):
        result = monitor.validate_receive("agent_b", "ch_ab")
        assert result is True

    def test_valid_receive_any_agent(self, monitor):
        result = monitor.validate_receive("agent_a", "ch_ab")
        assert result is True

    def test_valid_acquire(self, monitor):
        result = monitor.validate_acquire("agent_a", "lock_1")
        assert result is True

    def test_valid_acquire_counter(self, monitor):
        result = monitor.validate_acquire("agent_b", "counter_1")
        assert result is True

    def test_valid_release(self, monitor):
        result = monitor.validate_release("agent_a", "lock_1")
        assert result is True

    def test_valid_release_counter(self, monitor):
        result = monitor.validate_release("agent_b", "counter_1")
        assert result is True


# ---------------------------------------------------------------------------
# Invalid channel
# ---------------------------------------------------------------------------

class TestInvalidChannel:
    def test_send_nonexistent_channel(self, monitor):
        with pytest.raises(ProtocolViolation, match="does not exist"):
            monitor.validate_send("agent_a", "ch_nonexistent")

    def test_receive_nonexistent_channel(self, monitor):
        with pytest.raises(ProtocolViolation, match="does not exist"):
            monitor.validate_receive("agent_a", "ch_nonexistent")


# ---------------------------------------------------------------------------
# Invalid resource
# ---------------------------------------------------------------------------

class TestInvalidResource:
    def test_acquire_nonexistent_resource(self, monitor):
        with pytest.raises(ProtocolViolation, match="does not exist"):
            monitor.validate_acquire("agent_a", "nonexistent_lock")

    def test_release_nonexistent_resource(self, monitor):
        with pytest.raises(ProtocolViolation, match="does not exist"):
            monitor.validate_release("agent_a", "nonexistent_lock")


# ---------------------------------------------------------------------------
# Label validation
# ---------------------------------------------------------------------------

class TestLabelValidation:
    def test_invalid_label_raises(self, monitor):
        with pytest.raises(ProtocolViolation, match="not valid"):
            monitor.validate_send("agent_a", "ch_ab", label="unknown_label")

    def test_valid_label_passes(self, monitor):
        result = monitor.validate_send("agent_a", "ch_ab", label="request")
        assert result is True

    def test_no_label_passes(self, monitor):
        """Sending without a label is allowed."""
        result = monitor.validate_send("agent_a", "ch_ab", label=None)
        assert result is True

    def test_channel_without_labels_accepts_any(self):
        """Channel with no labels defined accepts any label."""
        mon = NullMonitor(NO_LABELS_IR)
        result = mon.validate_send("x", "ch_xy", label="anything")
        assert result is True


# ---------------------------------------------------------------------------
# Trace recording
# ---------------------------------------------------------------------------

class TestTrace:
    def test_empty_trace_initially(self, monitor):
        assert monitor.trace == []

    def test_operations_recorded_in_trace(self, monitor):
        monitor.validate_send("agent_a", "ch_ab", label="request")
        monitor.validate_receive("agent_b", "ch_ab")
        monitor.validate_acquire("agent_a", "lock_1")
        monitor.validate_release("agent_a", "lock_1")

        trace = monitor.trace
        assert len(trace) == 4
        assert trace[0].agent == "agent_a"
        assert trace[0].operation == "send"
        assert trace[0].target == "ch_ab"
        assert trace[0].label == "request"
        assert trace[1].operation == "receive"
        assert trace[2].operation == "acquire"
        assert trace[3].operation == "release"

    def test_trace_is_copy(self, monitor):
        """trace property returns a copy, not the internal list."""
        monitor.validate_send("agent_a", "ch_ab")
        t1 = monitor.trace
        t2 = monitor.trace
        assert t1 == t2
        assert t1 is not t2

    def test_failed_operations_not_in_trace(self, monitor):
        """Operations that raise ProtocolViolation are not recorded."""
        try:
            monitor.validate_send("agent_a", "ch_nonexistent")
        except ProtocolViolation:
            pass
        assert len(monitor.trace) == 0
