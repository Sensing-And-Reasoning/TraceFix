"""Real-TLC integration tests over benchmark protocols — the design&repair
stage end-to-end, with no LLM.

The unit tests (test_tlc_runner / test_trace_parser / test_error_formatter)
cover the repair core as pure functions on synthetic strings. This module runs
the *actual* Java/TLC toolchain on the verified benchmark specs shipped under
tests/fixtures/, exercising the whole inner chain on real data:

    generate_tlc_config → run_tlc → _parse_tlc_output → parse_trace → format_tlc_error

Two directions are checked:
  * known-good benchmark protocols must be classified as a real PASS, and
  * a coordination bug injected into a real benchmark protocol must be caught
    and turned into a usable repair prompt.

Skipped automatically when Java 17 or lib/tla2tools.jar is unavailable, so the
fast unit suite still runs anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracefix.pipeline.pipeline.pluscal_generator import generate_tlc_config
from tracefix.pipeline.pipeline.tlc_runner import run_tlc, JAVA_PATH, TLA2TOOLS_JAR
from tracefix.pipeline.pipeline.trace_parser import parse_trace
from tracefix.pipeline.pipeline.error_formatter import format_tlc_error

_FIXTURES = Path(__file__).parent / "fixtures"

_HAVE_TLC = Path(JAVA_PATH).exists() and Path(TLA2TOOLS_JAR).exists()
pytestmark = pytest.mark.skipif(
    not _HAVE_TLC, reason="needs Java 17 + lib/tla2tools.jar (real TLC)"
)

# Small benchmark protocols that each verify in well under a second. (Heavier
# fixtures like 11M/11H have 10^7+ states and belong in a slow/nightly lane.)
_FAST_PASS_TASKS = ["8E", "9E", "10E", "3E", "6E", "11E"]


def _load(task: str) -> tuple[dict, str]:
    ir = json.loads((_FIXTURES / task / "ir.json").read_text())
    tla = (_FIXTURES / task / "Protocol_translated.tla").read_text()
    return ir, tla


@pytest.mark.parametrize("task", _FAST_PASS_TASKS)
def test_benchmark_protocol_verifies(task: str):
    """A known-good benchmark protocol is classified as a genuine pass by the
    hardened verdict parser, against real TLC output (not a synthetic string)."""
    ir, tla = _load(task)
    r = run_tlc(tla, generate_tlc_config(ir), timeout=60)
    assert r.success is True, f"{task} should verify; got {r.violation_type}: {r.error_trace}"
    assert r.stats.get("states_generated", 0) > 0


def test_injected_orphan_lock_is_caught_and_explained():
    """Drop a lock release in a real benchmark protocol (8E) and confirm the
    full repair chain reacts: real TLC finds an error, the hardened classifier
    labels it, and the formatter produces an actionable repair prompt that
    points at the offending lock.

    Note: an orphaned lock is reachable as *either* a deadlock (another agent
    blocks forever on it) or a NoOrphanLocks safety violation (the holder
    terminates still holding it). TLC's parallel search may surface either, so
    we accept both — the point is the bug is caught and explained."""
    ir, tla = _load("8E")
    needle = 'migration_lock\' = "FREE"'
    assert tla.count(needle) >= 1, "fixture changed; update the injection target"
    broken = tla.replace(needle, "migration_lock' = migration_lock")

    r = run_tlc(broken, generate_tlc_config(ir), timeout=60)
    assert r.success is False, "injected orphan lock must NOT verify"
    assert r.violation_type in ("safety", "deadlock")

    trace = parse_trace(r.raw_output)
    assert trace, "a real counterexample trace must be extracted"
    # The over-capture fix holds on real TLC output: no variable in the final
    # state absorbed the trailing "N states generated, ..." summary line.
    assert all("states generated" not in v for v in trace[-1].variables.values())

    prompt = format_tlc_error(r, trace)
    assert "Verification Failure" in prompt
    assert "Protocol.tla" in prompt          # tells the agent where to fix
    assert "migration_lock" in prompt        # names the actual orphaned lock
    if r.violation_type == "safety":
        assert "NoOrphanLocks" in prompt
