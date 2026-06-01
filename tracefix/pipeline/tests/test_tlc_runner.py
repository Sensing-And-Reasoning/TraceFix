"""Unit tests for tracefix.pipeline/pipeline/tlc_runner.py — TLC verdict parsing.

`_parse_tlc_output` is the single most safety-critical pure function in the
repair pipeline: it decides whether a model-checking run PASSED or FAILED (and
how). A false "success" silently ships an *unverified* protocol — defeating the
entire point of tracefix. Yet it had zero direct tests; this file pins its
behavior and locks in the fail-closed hardening.

The raw TLC outputs below are synthetic but faithful: header/footer lines are
copied verbatim from a real passing run
(tracefix/runtime/sdk_adapter/examples/mas_doc_report/tlc_output.log), and the
counterexample blocks follow TLC's actual format (the same one trace_parser and
error_formatter already target).
"""

from __future__ import annotations

from tracefix.pipeline.pipeline.tlc_runner import _parse_tlc_output


# ── Faithful TLC output fixtures ─────────────────────────────────────────────

# Verbatim from the real passing run's header.
_HEADER = """\
TLC2 Version 2026.05.26.235334 (rev: 4ba7d88)
Running breadth-first search Model-Checking with fp 78 and seed 4763750931485722980 with 12 workers on 12 cores with 4096MB heap and 64MB offheap memory.
Parsing file /private/tmp/tlc_v3_jsi6fulm/Protocol.tla
Semantic processing of module Protocol
Starting... (2026-05-29 02:30:37)
Computing initial states...
Finished computing initial states: 1 distinct state generated at 2026-05-29 02:30:37."""

# Verbatim success footer (the exact pair TLC prints on a clean pass).
PASS_OUTPUT = _HEADER + """
Model checking completed. No error has been found.
  Estimates of the probability that TLC did not check all reachable states
  because two distinct states had the same fingerprint:
  calculated (optimistic):  val = 5.2E-17
65 states generated, 42 distinct states found, 0 states left on queue.
The depth of the complete state graph search is 16.
Finished in 00s at (2026-05-29 02:30:37)
"""

SAFETY_OUTPUT = _HEADER + """
Error: Invariant NoOrphanLocks is violated.
Error: The behavior up to this point is:
State 1: <Initial predicate>
/\\ pc = (researcherA :> "rA_acquire" @@ editor :> "ed_done")
/\\ locks = (doc_lock :> "FREE")
/\\ channels = (resA_to_editor :> <<>>)
/\\ counters = <<>>

State 2: <rA_acquire(researcherA) line 50, col 5 to line 52, col 30 of module Protocol>
/\\ pc = (researcherA :> "Done" @@ editor :> "ed_done")
/\\ locks = (doc_lock :> "researcherA")
/\\ channels = (resA_to_editor :> <<>>)
/\\ counters = <<>>

8 states generated, 5 distinct states found, 0 states left on queue.
Finished in 00s at (2026-05-29 02:30:37)
"""

DEADLOCK_OUTPUT = _HEADER + """
Error: Deadlock reached.
Error: The behavior up to this point is:
State 1: <Initial predicate>
/\\ pc = (researcherA :> "rA_acquire" @@ editor :> "ed_wait")
/\\ locks = (doc_lock :> "FREE")
/\\ channels = (resA_to_editor :> <<>>)
/\\ counters = <<>>

State 2: <rA_acquire(researcherA) line 50, col 5 to line 52, col 30 of module Protocol>
/\\ pc = (researcherA :> "rA_wait" @@ editor :> "ed_wait")
/\\ locks = (doc_lock :> "researcherA")
/\\ channels = (resA_to_editor :> <<>>)
/\\ counters = <<>>

5 states generated, 4 distinct states found, 0 states left on queue.
"""

ASSERT_OUTPUT = _HEADER + """
Error: The first argument of Assert evaluated to FALSE; the second argument was:
"Counter went negative"
Error: The behavior up to this point is:
State 1: <Initial predicate>
/\\ counters = (pool :> 0)

3 states generated, 2 distinct states found, 0 states left on queue.
"""

SEMANTIC_ERROR_OUTPUT = """\
TLC2 Version 2026.05.26.235334 (rev: 4ba7d88)
Parsing file /private/tmp/tlc_v3_jsi6fulm/Protocol.tla
Semantic processing of module Protocol
Error: Unknown operator: AcquireLockk.
"""

LIVENESS_OUTPUT = _HEADER + """
Error: Temporal properties were violated.
Error: The behavior up to this point is:
State 1: <Initial predicate>
/\\ pc = (researcherA :> "rA_loop")

4 states generated, 3 distinct states found, 0 states left on queue.
"""


# ── Standard verdicts (pin current, correct behavior) ────────────────────────

class TestStandardVerdicts:
    def test_pass(self):
        r = _parse_tlc_output(PASS_OUTPUT, elapsed=0.3)
        assert r.success is True
        assert r.violation_type is None
        assert r.stats["states_generated"] == 65
        assert r.stats["distinct_states"] == 42

    def test_safety_violation(self):
        r = _parse_tlc_output(SAFETY_OUTPUT, elapsed=0.1)
        assert r.success is False
        # "Error:" appears in the output, but the `is violated` branch must win.
        assert r.violation_type == "safety"
        assert r.error_trace and "State 1:" in r.error_trace

    def test_deadlock(self):
        r = _parse_tlc_output(DEADLOCK_OUTPUT, elapsed=0.1)
        assert r.success is False
        assert r.violation_type == "deadlock"

    def test_assertion_failure_is_safety(self):
        r = _parse_tlc_output(ASSERT_OUTPUT, elapsed=0.1)
        assert r.success is False
        assert r.violation_type == "safety"

    def test_semantic_error(self):
        r = _parse_tlc_output(SEMANTIC_ERROR_OUTPUT, elapsed=0.1)
        assert r.success is False
        assert r.violation_type == "error"

    def test_liveness_violation(self):
        r = _parse_tlc_output(LIVENESS_OUTPUT, elapsed=0.1)
        assert r.success is False
        assert r.violation_type == "liveness"

    def test_stats_parsed_even_on_failure(self):
        r = _parse_tlc_output(SAFETY_OUTPUT, elapsed=0.5)
        assert r.stats["states_generated"] == 8
        assert r.stats["distinct_states"] == 5
        assert r.stats["elapsed_seconds"] == 0.5


# ── Fail-closed hardening (the P3 spec) ──────────────────────────────────────
#
# These encode the rule "a verifier must PROVE a pass, never infer it from the
# absence of error markers." They fail against the old heuristic classifier and
# pass after the hardening.

class TestFailClosed:
    def test_states_but_no_verdict_is_not_success(self):
        """The dangerous case: TLC produced states but the run was cut off before
        any verdict (no 'Model checking completed', no failure marker). The old
        code returned success=True here — silently passing an unverified spec.
        Fail-closed: this must be a failure."""
        truncated = _HEADER + """
1200 states generated, 800 distinct states found, 1 states left on queue.
"""
        r = _parse_tlc_output(truncated, elapsed=2.0)
        assert r.success is False, "states-but-no-verdict must NOT be treated as pass"
        assert r.violation_type == "error"

    def test_pass_with_benign_error_substring_still_passes(self):
        """A clean pass that happens to contain the capitalized word 'Error'
        somewhere benign (e.g. a warning line). The old code gated success on the
        *absence* of 'Error' and so reported a false FAILURE. Positive
        confirmation ('Model checking completed' + 'No error has been found')
        must classify this as success regardless."""
        noisy_pass = _HEADER + """
Error reporting to the profiler is disabled.
Model checking completed. No error has been found.
65 states generated, 42 distinct states found, 0 states left on queue.
"""
        r = _parse_tlc_output(noisy_pass, elapsed=0.3)
        assert r.success is True, "positive completion must win over a benign 'Error' substring"

    def test_empty_output_is_failure(self):
        r = _parse_tlc_output("", elapsed=0.0)
        assert r.success is False
        assert r.violation_type == "error"
        assert r.error_trace  # never an empty string

    def test_garbage_output_is_failure(self):
        r = _parse_tlc_output("java.lang.OutOfMemoryError: Java heap space", elapsed=1.0)
        assert r.success is False
        assert r.violation_type == "error"
