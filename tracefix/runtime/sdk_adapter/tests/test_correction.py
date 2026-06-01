"""Monitoring Correction (Workstream B) — SDK-free / API-free unit tests.

Exercises the corrective path end-to-end through the real components:
StateTracker.legal_actions/check_op → CoordinationContext._guard (blocking) →
CoordToolDispatcher._handle_correction (bounded → honest failure). Uses a tiny
inline protocol so the test is self-contained (no benchmark, no workspace files).
"""

from __future__ import annotations

import asyncio

from tracefix.runtime.monitoring.monitor import ProtocolMonitor, StateGuidanceError
from tracefix.runtime.monitoring.state_tracker import StateTracker
from tracefix.runtime.monitoring.coord import CoordinationContext
from tracefix.runtime.monitoring.correction import CORRECTION_CAP
from tracefix.runtime.sdk_adapter.dispatch import CoordToolDispatcher

IR = {
    "agents": [{"id": "A"}, {"id": "B"}],
    "resources": [{"id": "L", "type": "Lock"}],
    "channels": [{"id": "a_to_b", "from": "A", "to": "B", "labels": ["go"]}],
}

# B must: receive "go" → acquire L → release L → done.  A: send "go" → done.
STATES = {
    "states": [
        {"id": "A_send", "agent": "A",
         "actions": [{"send": {"channel": "a_to_b", "label": "go"}, "next_state": "A_done"}]},
        {"id": "A_done", "agent": "A", "actions": []},
        {"id": "B_recv", "agent": "B",
         "actions": [{"receive": {"channel": "a_to_b"}, "next_state": "B_acq"}]},
        {"id": "B_acq", "agent": "B", "actions": [{"acquire": "L", "next_state": "B_rel"}]},
        {"id": "B_rel", "agent": "B", "actions": [{"release": "L", "next_state": "B_done"}]},
        {"id": "B_done", "agent": "B", "actions": []},
    ],
    "initial_states": {"A": "A_send", "B": "B_recv"},
}


def _coord(correction=True):
    return CoordinationContext(IR, ProtocolMonitor(IR),
                               tracker=StateTracker(STATES), correction=correction)


# --- StateTracker pure additions ---

class TestStateTrackerGuidance:
    def test_legal_actions(self):
        t = StateTracker(STATES)
        assert t.legal_actions("B") == [{"op": "receive", "channel": "a_to_b"}]
        assert t.legal_actions("A") == [{"op": "send", "channel": "a_to_b", "label": "go"}]

    def test_check_op_legal_and_illegal_no_mutation(self):
        t = StateTracker(STATES)
        ok, legal = t.check_op("B", "acquire", {"resource": "L"})  # B must receive first
        assert ok is False
        assert legal == [{"op": "receive", "channel": "a_to_b"}]
        assert t.current_states["B"] == "B_recv"  # position unchanged by the read-only check
        ok, legal = t.check_op("B", "receive", {"channel": "a_to_b"})
        assert ok is True and legal == []
        assert t.current_states["B"] == "B_recv"  # still not advanced (check_op is read-only)

    def test_correction_streak_resets_on_progress(self):
        t = StateTracker(STATES)
        t.check_op("B", "acquire", {"resource": "L"})
        t.check_op("B", "acquire", {"resource": "L"})
        assert t.correction_streak("B") == 2
        t.on_receive("B", "a_to_b", "go")  # legal move → new state
        assert t.correction_streak("B") == 0


# --- coord.py blocking gate ---

class TestCoordBlocking:
    def test_out_of_order_is_blocked_pre_effect(self):
        async def scenario():
            coord = _coord()
            try:
                await coord.acquire_lock("L", "B")
                assert False, "illegal acquire should have raised"
            except StateGuidanceError as e:
                assert e.legal_actions == [{"op": "receive", "channel": "a_to_b"}]
            assert coord.locks._locks.get("L") != "B"  # lock genuinely untouched
            # legal path works
            await coord.send("a_to_b", "go", "A")
            assert (await coord.receive("a_to_b", "B"))["status"] == "received"
            assert (await coord.acquire_lock("L", "B"))["status"] == "acquired"
        asyncio.run(scenario())

    def test_correction_off_by_default_is_soft(self):
        async def scenario():
            coord = _coord(correction=False)
            r = await coord.acquire_lock("L", "B")  # NOT blocked when correction is off
            assert r["status"] == "acquired"
            assert coord.tracker.violation_count == 1  # soft-recorded as before
        asyncio.run(scenario())


# --- dispatcher: corrective result + bounded honest failure ---

class TestDispatcherCorrection:
    def test_guidance_then_honest_fail_at_cap(self):
        async def scenario():
            coord = _coord()
            disp = CoordToolDispatcher(coord, "B")
            results = []
            for _ in range(CORRECTION_CAP):
                results.append(await disp.dispatch("acquire_lock", {"lock_id": "L"}))
            # earlier attempts: corrective guidance
            assert results[0]["error"] == "out_of_order"
            assert results[0]["legal_actions"] == [{"op": "receive", "channel": "a_to_b"}]
            assert results[0]["correction_attempt"] == 1
            # final attempt at the cap: honest failure
            assert results[-1]["error"] == "correction_limit"
            assert disp.correction_limit_exceeded is True
        asyncio.run(scenario())
