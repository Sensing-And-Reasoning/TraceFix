"""Tests for CoordinationContext."""

import asyncio
import json
from pathlib import Path

import pytest

from tracefix.runtime.monitoring.monitor import ProtocolMonitor, ProtocolViolation
from tracefix.runtime.monitoring.coord import CoordinationContext

_FIXTURES = Path(__file__).parent / "fixtures"
_3M_IR = _FIXTURES / "3M" / "ir.json"


@pytest.fixture
def ir_3m():
    with open(_3M_IR) as f:
        return json.load(f)


@pytest.fixture
def coord(ir_3m):
    monitor = ProtocolMonitor(ir_3m)
    return CoordinationContext(ir_3m, monitor)


# ---------------------------------------------------------------------------
# Lock operations
# ---------------------------------------------------------------------------

class TestLockOps:
    @pytest.mark.asyncio
    async def test_acquire_and_release(self, coord):
        result = await coord.acquire_lock("doc_lock", "researcherA")
        assert result["status"] == "acquired"
        result = await coord.release_lock("doc_lock", "researcherA")
        assert result["status"] == "released"

    @pytest.mark.asyncio
    async def test_release_by_non_holder_rejected(self, coord):
        """H2: a Lock may only be released by its current holder.

        validate_release only checks existence and release historically freed the
        lock unconditionally, so a non-holder's release silently freed another
        agent's lock (breaking mutual exclusion). It must raise instead and leave
        the real holder's ownership intact.
        """
        await coord.acquire_lock("doc_lock", "researcherA")
        with pytest.raises(ProtocolViolation):
            await coord.release_lock("doc_lock", "researcherB")  # B does not hold it
        # The lock was NOT freed — A still holds it.
        assert coord.locks._locks["doc_lock"] == "researcherA"
        # And it is genuinely still locked: B cannot acquire within the timeout.
        result = await coord.acquire_lock("doc_lock", "researcherB", timeout=0.1)
        assert result["status"] == "timeout"

    @pytest.mark.asyncio
    async def test_lock_contention_returns_timeout(self, coord):
        """Second agent gets 'timeout' when lock is held by another."""
        await coord.acquire_lock("doc_lock", "researcherA")

        result = await coord.acquire_lock("doc_lock", "researcherB", timeout=0.1)
        assert result["status"] == "timeout"

        # After release, B can acquire
        await coord.release_lock("doc_lock", "researcherA")
        result = await coord.acquire_lock("doc_lock", "researcherB")
        assert result["status"] == "acquired"

    @pytest.mark.asyncio
    async def test_acquire_wakes_on_release(self, coord):
        """Acquire wakes up immediately when another agent releases."""
        await coord.acquire_lock("doc_lock", "researcherA")

        async def release_later():
            await asyncio.sleep(0.2)
            await coord.release_lock("doc_lock", "researcherA")

        asyncio.create_task(release_later())
        import time
        t0 = time.monotonic()
        result = await coord.acquire_lock("doc_lock", "researcherB", timeout=5.0)
        elapsed = time.monotonic() - t0
        assert result["status"] == "acquired"
        assert elapsed < 1.0  # should wake up in ~0.2s, not wait 5s

    @pytest.mark.asyncio
    async def test_already_held(self, coord):
        """Same agent acquiring same lock twice gets 'already_held'."""
        await coord.acquire_lock("doc_lock", "researcherA")
        result = await coord.acquire_lock("doc_lock", "researcherA")
        assert result["status"] == "already_held"

    @pytest.mark.asyncio
    async def test_acquire_invalid_lock(self, coord):
        with pytest.raises(ProtocolViolation):
            await coord.acquire_lock("nonexistent", "researcherA")


# ---------------------------------------------------------------------------
# Channel operations
# ---------------------------------------------------------------------------

class TestChannelOps:
    @pytest.mark.asyncio
    async def test_send_and_receive(self, coord):
        result = await coord.send("resA_to_fc", "submit", "researcherA")
        assert result["status"] == "sent"

        result = await coord.receive("resA_to_fc", "factchecker")
        assert result["status"] == "received"
        assert result["label"] == "submit"

    @pytest.mark.asyncio
    async def test_receive_blocks_then_unblocks(self, coord):
        """Receive on empty channel blocks; send unblocks it."""
        received = asyncio.Event()

        async def receiver():
            result = await coord.receive("resA_to_fc", "factchecker")
            received.set()
            return result

        task = asyncio.create_task(receiver())
        await asyncio.sleep(0.01)
        assert not received.is_set(), "Should be blocked on empty channel"

        await coord.send("resA_to_fc", "submit", "researcherA")
        result = await asyncio.wait_for(task, timeout=1.0)
        assert result["label"] == "submit"

    @pytest.mark.asyncio
    async def test_fifo_order(self, coord):
        """Messages are received in FIFO order."""
        await coord.send("fc_to_resA", "pass", "factchecker")
        await coord.send("fc_to_resA", "flag", "factchecker")

        r1 = await coord.receive("fc_to_resA", "researcherA")
        r2 = await coord.receive("fc_to_resA", "researcherA")
        assert r1["label"] == "pass"
        assert r2["label"] == "flag"

    @pytest.mark.asyncio
    async def test_send_invalid_agent(self, coord):
        with pytest.raises(ProtocolViolation):
            await coord.send("resA_to_fc", "submit", "factchecker")

    @pytest.mark.asyncio
    async def test_receive_invalid_agent(self, coord):
        with pytest.raises(ProtocolViolation):
            await coord.receive("resA_to_fc", "researcherA")

    @pytest.mark.asyncio
    async def test_receive_timeout_on_empty(self, coord):
        """Receive on empty channel returns timeout after deadline."""
        result = await coord.receive("resA_to_fc", "factchecker", timeout=0.1)
        assert result["status"] == "timeout"
        assert result["channel"] == "resA_to_fc"

    @pytest.mark.asyncio
    async def test_receive_returns_before_timeout_when_message_arrives(self, coord):
        """Message arriving during wait returns immediately, not at timeout."""
        async def sender():
            await asyncio.sleep(0.05)
            await coord.send("resA_to_fc", "submit", "researcherA")

        asyncio.create_task(sender())
        result = await coord.receive("resA_to_fc", "factchecker", timeout=5.0)
        assert result["status"] == "received"
        assert result["label"] == "submit"


# ---------------------------------------------------------------------------
# Integration: multi-agent scenario
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Counter operations (unified via acquire_lock / release_lock)
# ---------------------------------------------------------------------------

# Minimal IR with a Counter resource
_COUNTER_IR = {
    "agents": [{"id": "agentA"}, {"id": "agentB"}],
    "resources": [{"id": "slots", "type": "Counter", "initial": 2}],
    "channels": [],
}


@pytest.fixture
def coord_counter():
    monitor = ProtocolMonitor(_COUNTER_IR)
    return CoordinationContext(_COUNTER_IR, monitor)


class TestCounterOps:
    @pytest.mark.asyncio
    async def test_acquire_decrements(self, coord_counter):
        """Acquiring a counter decrements it."""
        r = await coord_counter.acquire_lock("slots", "agentA")
        assert r["status"] == "acquired"
        assert r["remaining"] == 1

    @pytest.mark.asyncio
    async def test_acquire_until_zero(self, coord_counter):
        """Counter with initial=2 allows 2 acquires, then timeout."""
        r1 = await coord_counter.acquire_lock("slots", "agentA")
        assert r1["status"] == "acquired"
        r2 = await coord_counter.acquire_lock("slots", "agentB")
        assert r2["status"] == "acquired"
        r3 = await coord_counter.acquire_lock("slots", "agentA", timeout=0.1)
        assert r3["status"] == "timeout"
        assert r3["remaining"] == 0

    @pytest.mark.asyncio
    async def test_release_increments(self, coord_counter):
        """Releasing a counter increments it back."""
        await coord_counter.acquire_lock("slots", "agentA")
        await coord_counter.acquire_lock("slots", "agentB")
        r = await coord_counter.release_lock("slots", "agentA")
        assert r["status"] == "released"
        assert r["remaining"] == 1
        # Now can acquire again
        r2 = await coord_counter.acquire_lock("slots", "agentA")
        assert r2["status"] == "acquired"

    @pytest.mark.asyncio
    async def test_counter_no_already_held(self, coord_counter):
        """Counter has no 'already_held' — same agent can acquire multiple slots."""
        r1 = await coord_counter.acquire_lock("slots", "agentA")
        assert r1["status"] == "acquired"
        r2 = await coord_counter.acquire_lock("slots", "agentA")
        assert r2["status"] == "acquired"


# ---------------------------------------------------------------------------
# Integration: multi-agent scenario
# ---------------------------------------------------------------------------

class TestMultiAgent:
    @pytest.mark.asyncio
    async def test_researcher_factchecker_flow(self, coord):
        """ResearcherA submits → factchecker receives → sends pass → researcherA receives."""
        await coord.acquire_lock("doc_lock", "researcherA")
        await coord.release_lock("doc_lock", "researcherA")
        await coord.send("resA_to_fc", "submit", "researcherA")

        result = await coord.receive("resA_to_fc", "factchecker")
        assert result["label"] == "submit"

        await coord.send("fc_to_resA", "pass", "factchecker")
        result = await coord.receive("fc_to_resA", "researcherA")
        assert result["label"] == "pass"


# ---------------------------------------------------------------------------
# Issue 1: Condition-based signaling (no signal loss)
# ---------------------------------------------------------------------------

class TestConditionSignaling:
    @pytest.mark.asyncio
    async def test_no_signal_loss_on_release(self, coord):
        """Release during acquire wait wakes the waiter immediately (Condition)."""
        await coord.acquire_lock("doc_lock", "researcherA")

        async def release_soon():
            await asyncio.sleep(0.05)
            await coord.release_lock("doc_lock", "researcherA")

        asyncio.create_task(release_soon())
        import time
        t0 = time.monotonic()
        result = await coord.acquire_lock("doc_lock", "researcherB", timeout=5.0)
        elapsed = time.monotonic() - t0
        assert result["status"] == "acquired"
        assert elapsed < 1.0  # should not wait for full timeout


# ---------------------------------------------------------------------------
# Observability plane: report_progress beacons + agent.phase emission
# ---------------------------------------------------------------------------

class _FakeBus:
    def __init__(self):
        self.events = []

    async def emit(self, event_type, data=None):
        self.events.append((event_type, data or {}))


def _phase_states():
    """researcherA: acquire doc_lock -> [write] (skip, business) -> release -> done."""
    return {
        "initial_states": {"researcherA": "rA_acquire"},
        "states": [
            {"id": "rA_acquire", "agent": "researcherA",
             "actions": [{"next_state": "rA_write", "acquire": "doc_lock"}]},
            {"id": "rA_write", "agent": "researcherA", "task": "write the section",
             "actions": [{"next_state": "rA_release"}]},
            {"id": "rA_release", "agent": "researcherA",
             "actions": [{"next_state": "rA_done", "release": "doc_lock"}]},
            {"id": "rA_done", "agent": "researcherA", "actions": []},
        ],
    }


class TestReportProgress:
    @pytest.mark.asyncio
    async def test_records_beacon_and_returns_ok(self, coord):
        res = await coord.report_progress("generating_figure", "researcherA")
        assert res == {"status": "ok", "label": "generating_figure"}
        assert len(coord.beacons) == 1
        b = coord.beacons[0]
        assert b["agent"] == "researcherA" and b["label"] == "generating_figure"
        assert isinstance(b["ts"], float)

    @pytest.mark.asyncio
    async def test_no_bus_does_not_raise(self, coord):
        res = await coord.report_progress("x", "researcherA")  # coord has event_bus=None
        assert res["status"] == "ok"

    @pytest.mark.asyncio
    async def test_emits_agent_progress(self, ir_3m):
        bus = _FakeBus()
        coord = CoordinationContext(ir_3m, ProtocolMonitor(ir_3m), event_bus=bus)
        await coord.report_progress("phase-x", "researcherA")
        assert ("agent.progress",
                {"agent_id": "researcherA", "label": "phase-x"}) in bus.events

    @pytest.mark.asyncio
    async def test_non_enforced_no_violation_no_state_change(self, ir_3m):
        from tracefix.runtime.monitoring.state_tracker import StateTracker
        tracker = StateTracker(_phase_states())
        coord = CoordinationContext(ir_3m, ProtocolMonitor(ir_3m),
                                    tracker=tracker, correction=True)
        before = dict(tracker.current_states)
        res = await coord.report_progress("anything", "researcherA")
        assert res["status"] == "ok"
        assert tracker.violation_count == 0
        assert dict(tracker.current_states) == before  # coordination untouched


class TestAgentPhaseEmission:
    @pytest.mark.asyncio
    async def test_phase_emitted_on_skip_then_cleared(self, ir_3m):
        from tracefix.runtime.monitoring.state_tracker import StateTracker
        bus = _FakeBus()
        tracker = StateTracker(_phase_states())
        coord = CoordinationContext(ir_3m, ProtocolMonitor(ir_3m),
                                    tracker=tracker, event_bus=bus)
        await coord.acquire_lock("doc_lock", "researcherA")
        phases = [d for (t, d) in bus.events if t == "agent.phase"]
        assert any(d["to_phase"] == "rA_write" and d["task"] == "write the section"
                   for d in phases)
        await coord.release_lock("doc_lock", "researcherA")
        phases = [d for (t, d) in bus.events if t == "agent.phase"]
        assert phases[-1]["to_phase"] is None  # cleared after release

    @pytest.mark.asyncio
    async def test_no_signal_loss_on_send(self, coord):
        """Send during receive wait wakes the receiver immediately (Condition)."""
        async def send_soon():
            await asyncio.sleep(0.05)
            await coord.send("resA_to_fc", "submit", "researcherA")

        asyncio.create_task(send_soon())
        import time
        t0 = time.monotonic()
        result = await coord.receive("resA_to_fc", "factchecker", timeout=5.0)
        elapsed = time.monotonic() - t0
        assert result["status"] == "received"
        assert result["label"] == "submit"
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_multiple_waiters_on_same_resource(self, coord):
        """Multiple agents waiting on the same lock — all get notified."""
        await coord.acquire_lock("doc_lock", "researcherA")

        results = []

        async def waiter(agent_id):
            r = await coord.acquire_lock("doc_lock", agent_id, timeout=2.0)
            results.append((agent_id, r["status"]))

        t1 = asyncio.create_task(waiter("researcherB"))
        t2 = asyncio.create_task(waiter("factchecker"))
        await asyncio.sleep(0.05)

        # Release → one gets it, the other waits
        await coord.release_lock("doc_lock", "researcherA")
        await asyncio.sleep(0.1)

        # Release the one that acquired
        for agent_id, status in results:
            if status == "acquired":
                await coord.release_lock("doc_lock", agent_id)
                break

        await asyncio.gather(t1, t2)
        statuses = [s for _, s in results]
        assert statuses.count("acquired") == 2


# ---------------------------------------------------------------------------
# Issue 2: Per-agent lock for async-safe tracker calls
# ---------------------------------------------------------------------------

class TestPerAgentLock:
    @pytest.mark.asyncio
    async def test_agent_locks_initialized(self, coord):
        """Per-agent locks are created for all agents in IR."""
        assert "researcherA" in coord._agent_locks
        assert "researcherB" in coord._agent_locks
        assert "factchecker" in coord._agent_locks
        assert isinstance(coord._agent_locks["researcherA"], asyncio.Lock)

    @pytest.mark.asyncio
    async def test_concurrent_receives_with_tracker(self):
        """Concurrent receives for the same agent serialize tracker calls."""
        # Minimal IR with 2 channels into the same agent
        ir = {
            "agents": [{"id": "sender"}, {"id": "receiver"}],
            "resources": [],
            "channels": [
                {"id": "ch1", "from": "sender", "to": "receiver", "labels": ["msg"]},
                {"id": "ch2", "from": "sender", "to": "receiver", "labels": ["msg"]},
            ],
        }
        from tracefix.runtime.monitoring.state_tracker import StateTracker
        states_data = {
            "initial_states": {"sender": "s0", "receiver": "r0"},
            "states": [
                # Sender: s0 → send ch1+ch2 compound → s1_done
                {"id": "s0", "agent": "sender", "actions": [
                    {"next_state": "s1_done", "send": [
                        {"channel": "ch1", "label": "msg"},
                        {"channel": "ch2", "label": "msg"},
                    ]},
                ]},
                {"id": "s1_done", "agent": "sender", "actions": []},
                # Receiver: r0 → receive ch1+ch2 compound → r1_done
                {"id": "r0", "agent": "receiver", "actions": [
                    {"next_state": "r1_done",
                     "receive": [
                         {"channel": "ch1", "label": "msg"},
                         {"channel": "ch2", "label": "msg"},
                     ]},
                ]},
                {"id": "r1_done", "agent": "receiver", "actions": []},
            ],
        }
        monitor = ProtocolMonitor(ir)
        tracker = StateTracker(states_data)
        coord = CoordinationContext(ir, monitor, tracker=tracker)

        # Pre-send messages so receives don't block
        await coord.send("ch1", "msg", "sender")
        await coord.send("ch2", "msg", "sender")

        # Concurrent receives for the same agent
        r1, r2 = await asyncio.gather(
            coord.receive("ch1", "receiver", timeout=1.0),
            coord.receive("ch2", "receiver", timeout=1.0),
        )
        assert r1["status"] == "received"
        assert r2["status"] == "received"
        # No violations — tracker handled both correctly under serialization
        assert tracker.violation_count == 0


# ---------------------------------------------------------------------------
# poll_channels tests (Category B: mixed receive+send either/or)
# ---------------------------------------------------------------------------

# IR with 3 senders → 1 receiver (models 10M builder check pattern)
_MULTI_CH_IR = {
    "agents": [{"id": "senderA"}, {"id": "senderB"}, {"id": "senderC"}, {"id": "receiver"}],
    "resources": [],
    "channels": [
        {"id": "chA", "from": "senderA", "to": "receiver", "labels": ["msg"]},
        {"id": "chB", "from": "senderB", "to": "receiver", "labels": ["msg"]},
        {"id": "chC", "from": "senderC", "to": "receiver", "labels": ["msg"]},
    ],
}


@pytest.fixture
def coord_multi():
    monitor = ProtocolMonitor(_MULTI_CH_IR)
    return CoordinationContext(_MULTI_CH_IR, monitor)


class TestPollChannels:
    @pytest.mark.asyncio
    async def test_poll_with_pending_message(self, coord_multi):
        """poll_channels returns the first pending message immediately."""
        await coord_multi.send("chB", "msg", "senderB")
        result = await coord_multi.poll_channels(["chA", "chB", "chC"], "receiver")
        assert result["status"] == "received"
        assert result["channel"] == "chB"
        assert result["label"] == "msg"

    @pytest.mark.asyncio
    async def test_poll_no_messages(self, coord_multi):
        """poll_channels returns 'none' immediately when no messages pending."""
        import time
        t0 = time.monotonic()
        result = await coord_multi.poll_channels(["chA", "chB", "chC"], "receiver")
        elapsed = time.monotonic() - t0
        assert result["status"] == "none"
        assert set(result["channels"]) == {"chA", "chB", "chC"}
        assert elapsed < 0.1  # truly non-blocking

    @pytest.mark.asyncio
    async def test_poll_returns_first_channel_with_message(self, coord_multi):
        """poll_channels returns the first channel (in order) that has a message."""
        await coord_multi.send("chA", "msg", "senderA")
        await coord_multi.send("chC", "msg", "senderC")
        result = await coord_multi.poll_channels(["chA", "chB", "chC"], "receiver")
        assert result["channel"] == "chA"  # first in list wins

    @pytest.mark.asyncio
    async def test_poll_consumes_message(self, coord_multi):
        """poll_channels consumes the message (not left in queue)."""
        await coord_multi.send("chA", "msg", "senderA")
        r1 = await coord_multi.poll_channels(["chA"], "receiver")
        assert r1["status"] == "received"
        r2 = await coord_multi.poll_channels(["chA"], "receiver")
        assert r2["status"] == "none"

    @pytest.mark.asyncio
    async def test_poll_surfaces_content_ref(self):
        """poll_channels surfaces the opaque content ref (claim-check), not a body —
        channels are flag-only; the payload lives in the data plane."""
        ir = {"agents": [{"id": "s"}, {"id": "r"}], "resources": [],
              "channels": [{"id": "ch", "from": "s", "to": "r",
                            "labels": ["rev"], "content_labels": ["rev"]}]}
        coord = CoordinationContext(ir, ProtocolMonitor(ir))
        posted = await coord.post_content("data payload", "s")
        await coord.send("ch", "rev", "s", ref=posted["ref"])
        result = await coord.poll_channels(["ch"], "r")
        assert result["status"] == "received" and result["ref"] == posted["ref"]
        assert "body" not in result
        assert (await coord.get_content(result["ref"], "r"))["content"] == "data payload"

    @pytest.mark.asyncio
    async def test_poll_invalid_channel(self, coord_multi):
        """poll_channels raises ProtocolViolation for unauthorized channel."""
        with pytest.raises(ProtocolViolation):
            await coord_multi.poll_channels(["chA"], "senderA")  # senderA can't receive on chA


# ---------------------------------------------------------------------------
# receive_any tests (Category A: pure receive either/or)
# ---------------------------------------------------------------------------

class TestReceiveAny:
    @pytest.mark.asyncio
    async def test_receive_any_with_pending(self, coord_multi):
        """receive_any returns immediately when a message is already pending."""
        await coord_multi.send("chC", "msg", "senderC")
        result = await coord_multi.receive_any(["chA", "chB", "chC"], "receiver")
        assert result["status"] == "received"
        assert result["channel"] == "chC"
        assert result["label"] == "msg"

    @pytest.mark.asyncio
    async def test_receive_any_wakes_on_send(self, coord_multi):
        """receive_any wakes up when a message arrives on any watched channel."""
        async def send_later():
            await asyncio.sleep(0.1)
            await coord_multi.send("chB", "msg", "senderB")

        asyncio.create_task(send_later())
        import time
        t0 = time.monotonic()
        result = await coord_multi.receive_any(
            ["chA", "chB", "chC"], "receiver", timeout=5.0)
        elapsed = time.monotonic() - t0
        assert result["status"] == "received"
        assert result["channel"] == "chB"
        assert elapsed < 1.0  # should wake up quickly, not wait 5s

    @pytest.mark.asyncio
    async def test_receive_any_timeout(self, coord_multi):
        """receive_any returns timeout when no messages arrive."""
        import time
        t0 = time.monotonic()
        result = await coord_multi.receive_any(
            ["chA", "chB"], "receiver", timeout=0.2)
        elapsed = time.monotonic() - t0
        assert result["status"] == "timeout"
        assert set(result["channels"]) == {"chA", "chB"}
        assert elapsed >= 0.15  # waited close to timeout

    @pytest.mark.asyncio
    async def test_receive_any_surfaces_content_ref(self):
        """receive_any surfaces the opaque content ref (claim-check), not a body."""
        ir = {"agents": [{"id": "s"}, {"id": "r"}], "resources": [],
              "channels": [{"id": "ch", "from": "s", "to": "r",
                            "labels": ["rev"], "content_labels": ["rev"]}]}
        coord = CoordinationContext(ir, ProtocolMonitor(ir))
        posted = await coord.post_content("hello", "s")
        await coord.send("ch", "rev", "s", ref=posted["ref"])
        result = await coord.receive_any(["ch"], "r")
        assert result["status"] == "received" and result["ref"] == posted["ref"]
        assert "body" not in result

    @pytest.mark.asyncio
    async def test_receive_any_consumes_message(self, coord_multi):
        """receive_any consumes the message from the channel."""
        await coord_multi.send("chA", "msg", "senderA")
        r1 = await coord_multi.receive_any(["chA"], "receiver", timeout=0.1)
        assert r1["status"] == "received"
        r2 = await coord_multi.receive_any(["chA"], "receiver", timeout=0.1)
        assert r2["status"] == "timeout"

    @pytest.mark.asyncio
    async def test_receive_any_invalid_channel(self, coord_multi):
        """receive_any raises ProtocolViolation for unauthorized channel."""
        with pytest.raises(ProtocolViolation):
            await coord_multi.receive_any(["chA"], "senderA")  # senderA can't receive
