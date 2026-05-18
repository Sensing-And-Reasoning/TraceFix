"""Tests for ProtocolMonitor."""

import json
from pathlib import Path

import pytest

from tracefix.runtime.monitoring.monitor import ProtocolMonitor, ProtocolViolation

_FIXTURES = Path(__file__).parent / "fixtures"
_3M_IR = _FIXTURES / "3M" / "ir.json"


@pytest.fixture
def ir_3m():
    with open(_3M_IR) as f:
        return json.load(f)


@pytest.fixture
def monitor(ir_3m):
    return ProtocolMonitor(ir_3m)


# ---------------------------------------------------------------------------
# Valid operations
# ---------------------------------------------------------------------------

class TestValidOperations:
    def test_send_valid(self, monitor):
        assert monitor.validate_send("researcherA", "resA_to_fc", "submit")

    def test_receive_valid(self, monitor):
        assert monitor.validate_receive("factchecker", "resA_to_fc")

    def test_acquire_valid(self, monitor):
        assert monitor.validate_acquire("researcherA", "doc_lock")

    def test_release_valid(self, monitor):
        assert monitor.validate_release("researcherA", "doc_lock")

    def test_send_no_label(self, monitor):
        """Send without label should pass even if channel has labels."""
        assert monitor.validate_send("researcherA", "resA_to_fc")

    def test_trace_records(self, monitor):
        monitor.validate_send("researcherA", "resA_to_fc", "submit")
        monitor.validate_acquire("researcherA", "doc_lock")
        assert len(monitor.trace) == 2
        assert monitor.trace[0].operation == "send"
        assert monitor.trace[1].operation == "acquire"


# ---------------------------------------------------------------------------
# Invalid operations
# ---------------------------------------------------------------------------

class TestInvalidOperations:
    def test_send_wrong_agent(self, monitor):
        """factchecker cannot send on resA_to_fc (from=researcherA)."""
        with pytest.raises(ProtocolViolation, match="cannot send"):
            monitor.validate_send("factchecker", "resA_to_fc", "submit")

    def test_send_wrong_channel(self, monitor):
        """researcherA cannot send on resB_to_fc."""
        with pytest.raises(ProtocolViolation, match="cannot send"):
            monitor.validate_send("researcherA", "resB_to_fc", "submit")

    def test_send_invalid_label(self, monitor):
        """resA_to_fc only allows 'submit', not 'bogus'."""
        with pytest.raises(ProtocolViolation, match="not valid"):
            monitor.validate_send("researcherA", "resA_to_fc", "bogus")

    def test_receive_wrong_agent(self, monitor):
        """researcherA cannot receive on resA_to_fc (to=factchecker)."""
        with pytest.raises(ProtocolViolation, match="cannot receive"):
            monitor.validate_receive("researcherA", "resA_to_fc")

    def test_receive_wrong_channel(self, monitor):
        with pytest.raises(ProtocolViolation, match="cannot receive"):
            monitor.validate_receive("factchecker", "fc_to_resA")

    def test_acquire_unknown_lock(self, monitor):
        with pytest.raises(ProtocolViolation, match="Unknown resource"):
            monitor.validate_acquire("researcherA", "nonexistent_lock")

    def test_release_unknown_lock(self, monitor):
        with pytest.raises(ProtocolViolation, match="Unknown resource"):
            monitor.validate_release("researcherA", "nonexistent_lock")

    def test_unknown_agent_send(self, monitor):
        with pytest.raises(ProtocolViolation, match="Unknown agent"):
            monitor.validate_send("ghost", "resA_to_fc", "submit")

    def test_unknown_agent_acquire(self, monitor):
        with pytest.raises(ProtocolViolation, match="Unknown agent"):
            monitor.validate_acquire("ghost", "doc_lock")
