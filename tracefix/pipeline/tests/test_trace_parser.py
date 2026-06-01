"""Unit tests for tracefix.pipeline/pipeline/trace_parser.py.

`parse_trace` turns a raw TLC counterexample into structured TraceSteps that
error_formatter renders into the repair prompt. Format follows TLC's actual
output (`State N: <Action>` followed by `/\\ var = value` lines, values may
wrap across lines).
"""

from __future__ import annotations

from tracefix.pipeline.pipeline.trace_parser import parse_trace, TraceStep


SAFETY_TRACE = """\
Error: Invariant NoOrphanLocks is violated.
Error: The behavior up to this point is:
State 1: <Initial predicate>
/\\ pc = (researcherA :> "rA_acquire" @@ editor :> "ed_done")
/\\ locks = (doc_lock :> "FREE")
/\\ channels = (resA_to_editor :> <<>>)

State 2: <rA_acquire(researcherA) line 50, col 5 to line 52, col 30 of module Protocol>
/\\ pc = (researcherA :> "Done" @@ editor :> "ed_done")
/\\ locks = (doc_lock :> "researcherA")
/\\ channels = (resA_to_editor :> <<>>)

8 states generated, 5 distinct states found, 0 states left on queue.
"""


class TestParseTrace:
    def test_extracts_all_states(self):
        steps = parse_trace(SAFETY_TRACE)
        assert len(steps) == 2
        assert all(isinstance(s, TraceStep) for s in steps)

    def test_state_numbers_and_actions(self):
        steps = parse_trace(SAFETY_TRACE)
        assert steps[0].state_num == 1
        assert steps[0].action == "Initial predicate"
        assert steps[1].state_num == 2
        # parse_trace keeps the raw action (line refs are stripped later by the
        # formatter, not here).
        assert steps[1].action.startswith("rA_acquire(researcherA)")
        assert "line 50" in steps[1].action

    def test_variables_captured(self):
        steps = parse_trace(SAFETY_TRACE)
        v = steps[1].variables
        assert set(v) == {"pc", "locks", "channels"}
        assert v["locks"] == '(doc_lock :> "researcherA")'
        assert v["channels"] == "(resA_to_editor :> <<>>)"

    def test_multiline_variable_value_is_joined(self):
        """A `/\\ var = ...` value that wraps onto continuation lines (no leading
        `/\\`) is appended to the current variable."""
        wrapped = """\
State 1: <Initial predicate>
/\\ pc = ( researcherA :> "rA_acquire"
   @@ editor :> "ed_wait" )
/\\ locks = (doc_lock :> "FREE")
"""
        steps = parse_trace(wrapped)
        assert len(steps) == 1
        assert steps[0].variables["pc"] == '( researcherA :> "rA_acquire" @@ editor :> "ed_wait" )'
        assert steps[0].variables["locks"] == '(doc_lock :> "FREE")'

    def test_empty_output_returns_empty_list(self):
        assert parse_trace("") == []

    def test_output_without_states_returns_empty(self):
        assert parse_trace("Model checking completed. No error has been found.") == []

    def test_single_state(self):
        steps = parse_trace("State 1: <Initial predicate>\n/\\ x = 1\n")
        assert len(steps) == 1
        assert steps[0].state_num == 1
        assert steps[0].variables == {"x": "1"}
