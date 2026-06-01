"""Unit tests for tracefix.pipeline/pipeline/error_formatter.py.

`format_tlc_error` turns a TLC verdict + trace into the repair prompt the agent
sees. This is the "repair" half of the design&repair stage and had no coverage.
The tests check that each violation type produces a prompt with the right
diagnosis, the invariant explanation (when known), the deadlock-cause inference,
and that long traces are truncated to a readable tail.
"""

from __future__ import annotations

from tracefix.pipeline.pipeline.error_formatter import format_tlc_error
from tracefix.pipeline.pipeline.tlc_runner import TLCResult
from tracefix.pipeline.pipeline.trace_parser import TraceStep


def _safety(raw: str) -> TLCResult:
    return TLCResult(success=False, violation_type="safety", raw_output=raw)


class TestSafety:
    def test_known_invariant_explained(self):
        tlc = _safety("Error: Invariant NoOrphanLocks is violated.")
        trace = [TraceStep(1, "Initial predicate",
                           {"locks": '(doc_lock :> "researcherA")'})]
        out = format_tlc_error(tlc, trace)
        assert "SAFETY VIOLATION" in out
        assert "NoOrphanLocks" in out
        # the human-readable meaning for this invariant is injected
        assert "still held" in out
        assert "Reading guide" in out

    def test_unknown_invariant_lists_candidates(self):
        tlc = _safety("Error: some unrecognized safety failure")
        out = format_tlc_error(tlc, [TraceStep(1, "Initial predicate", {})])
        assert "SAFETY VIOLATION" in out
        # falls back to enumerating the candidate invariants
        for inv in ("NoOrphanLocks", "ChannelsDrained", "MutualExclusion", "TypeInvariant"):
            assert inv in out


class TestDeadlock:
    def test_infers_lock_contention_and_empty_channel(self):
        final = TraceStep(5, "ed_receive(editor) line 70, col 5 of module Protocol", {
            "pc": '(researcherA :> "rA_wait" @@ editor :> "ed_receive")',
            "locks": '(doc_lock :> "researcherA")',
            "channels": "(resA_to_editor :> <<>>)",
            "counters": "<<>>",
        })
        tlc = TLCResult(success=False, violation_type="deadlock",
                        raw_output="Error: Deadlock reached.")
        out = format_tlc_error(tlc, [TraceStep(1, "Initial predicate", {}), final])
        assert "DEADLOCK" in out
        assert "Inferred cause" in out
        assert "Lock contention" in out and "doc_lock" in out
        assert "Empty channels" in out and "resA_to_editor" in out

    def test_infers_counter_at_zero(self):
        final = TraceStep(3, "acquire line 1 of module Protocol", {
            "locks": "(doc_lock :> \"FREE\")",
            "channels": "(c :> <<>>)",
            "counters": "(pool :> 0)",
        })
        tlc = TLCResult(success=False, violation_type="deadlock", raw_output="Deadlock reached")
        out = format_tlc_error(tlc, [final])
        assert "Counter at zero" in out and "pool" in out


class TestErrorAndLiveness:
    def test_error_includes_details(self):
        tlc = TLCResult(success=False, violation_type="error",
                        error_trace="Error: Unknown operator: AcquireLockk.",
                        raw_output="Error: Unknown operator: AcquireLockk.")
        out = format_tlc_error(tlc, [])
        assert "TLC ERROR" in out
        assert "Unknown operator" in out

    def test_liveness_note(self):
        tlc = TLCResult(success=False, violation_type="liveness",
                        raw_output="Error: Temporal properties were violated.")
        out = format_tlc_error(tlc, [TraceStep(1, "Initial predicate", {})])
        assert "LIVENESS" in out


class TestTraceTruncation:
    def test_short_trace_shown_in_full(self):
        trace = [TraceStep(i, f"act{i}", {"pc": f"s{i}"}) for i in range(1, 5)]
        out = format_tlc_error(_safety("Error: Invariant MutualExclusion is violated."), trace)
        assert "Complete trace (4 states)" in out

    def test_long_trace_truncated_to_tail(self):
        trace = [TraceStep(i, f"act{i}", {"pc": f"s{i}"}) for i in range(1, 16)]  # 15 states
        out = format_tlc_error(_safety("Error: Invariant MutualExclusion is violated."), trace)
        assert "Last 5 states of a 15-state trace" in out
        assert "tlc_output.log" in out   # told to read the full log
        assert "State 15:" in out         # tail is present
        assert "State 1:" not in out      # early states omitted from the inline trace

    def test_no_trace_available(self):
        out = format_tlc_error(_safety("Error: Invariant NoOrphanLocks is violated."), [])
        assert "No counterexample trace available." in out
