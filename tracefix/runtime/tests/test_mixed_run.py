"""Tests for the mixed-harness driver's pure helpers (agent split validation)."""

from __future__ import annotations

from tracefix.runtime.mixed_run import _split, validate_split

ALL = ["RESEARCHER_FM", "RESEARCHER_RT", "RESEARCHER_EVAL", "PLOTTER", "CHECKER", "APPROVER"]


def test_split_parses_csv():
    assert _split("A, B ,C") == ["A", "B", "C"]
    assert _split("") == []
    assert _split(None) == []


def test_validate_split_ok():
    err = validate_split(ALL, ["RESEARCHER_FM", "RESEARCHER_RT", "PLOTTER"],
                         ["RESEARCHER_EVAL", "CHECKER", "APPROVER"])
    assert err is None


def test_validate_split_missing_agent_is_rejected():
    # APPROVER assigned to neither harness → would stall the protocol.
    err = validate_split(ALL, ["RESEARCHER_FM", "RESEARCHER_RT", "PLOTTER"],
                         ["RESEARCHER_EVAL", "CHECKER"])
    assert err and "missing" in err and "APPROVER" in err


def test_validate_split_duplicate_is_rejected():
    err = validate_split(ALL, ["PLOTTER", "RESEARCHER_FM", "RESEARCHER_RT"],
                         ["PLOTTER", "RESEARCHER_EVAL", "CHECKER", "APPROVER"])
    assert err and "duplicates" in err and "PLOTTER" in err


def test_validate_split_unknown_agent_is_rejected():
    err = validate_split(ALL, ["RESEARCHER_FM", "GHOST"],
                         ["RESEARCHER_RT", "RESEARCHER_EVAL", "PLOTTER", "CHECKER", "APPROVER"])
    assert err and "unknown" in err and "GHOST" in err
