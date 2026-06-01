"""Unit tests for tracefix.pipeline/pipeline/pluscal_compiler.py error handling.

The PlusCal *compile* error path (pcal.trans fails before TLC ever runs) is the
failure mode that actually occurred in practice — the only real pipeline run
captured in this repo failed exactly here ("Expected ':=' but found 'skip'").
We don't shell out to Java; we test the pure error-extraction helpers that turn
pcal.trans output into the repair message, including the source-context pointer.
"""

from __future__ import annotations

from tracefix.pipeline.pipeline.pluscal_compiler import (
    _has_pcal_error, _extract_pcal_error,
)

# Verbatim pcal.trans phrasing from a real failed run (line number scaled to the
# small fixture below).
REAL_PCAL_ERROR = 'Unrecoverable error:\n-- Expected ":=" but found "skip"\nline 6, column 5.'

FIXTURE_TLA = "\n".join([
    "---- MODULE Protocol ----",   # 1
    "EXTENDS Integers, Sequences",  # 2
    "(* --algorithm proto",         # 3
    'process A = "a"',              # 4
    "  begin A_research:",          # 5
    "    skip;",                    # 6  <- offending line
    "  end process;",               # 7
    "end algorithm; *)",            # 8
])


class TestHasPcalError:
    def test_detects_unrecoverable_error(self):
        assert _has_pcal_error(REAL_PCAL_ERROR) is True

    def test_detects_expected_token(self):
        assert _has_pcal_error('-- Expected ":=" but found "x" line 3.') is True

    def test_detects_unclosed_block(self):
        assert _has_pcal_error("Error: comment was not closed") is True

    def test_clean_output_is_not_an_error(self):
        assert _has_pcal_error("Translation written to Protocol.tla") is False


class TestExtractPcalError:
    def test_includes_error_message(self):
        msg = _extract_pcal_error(REAL_PCAL_ERROR, FIXTURE_TLA)
        assert "Expected" in msg
        assert 'found "skip"' in msg

    def test_includes_source_context_with_pointer(self):
        msg = _extract_pcal_error(REAL_PCAL_ERROR, FIXTURE_TLA)
        assert "Source context:" in msg
        assert ">>>" in msg              # the offending line is marked
        assert "skip;" in msg            # ...and the actual source is shown
        assert "6 |" in msg              # with its line number

    def test_pointer_targets_the_reported_line(self):
        msg = _extract_pcal_error(REAL_PCAL_ERROR, FIXTURE_TLA)
        # the ">>>" marker must sit on line 6 (the skip), not a neighbor
        marked = [ln for ln in msg.splitlines() if ln.startswith(">>>")]
        assert len(marked) == 1
        assert "skip;" in marked[0]

    def test_no_line_number_falls_back_gracefully(self):
        msg = _extract_pcal_error("Unrecoverable error: something broke", FIXTURE_TLA)
        assert msg  # non-empty
        assert "Source context:" not in msg  # nothing to point at
