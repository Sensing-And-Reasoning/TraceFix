"""Tests for tracefix.runtime.enforcement live visualization: event bus, engine event emission."""

import asyncio

import pytest

from tracefix.runtime.enforcement.event_bus import EventBus, Event
from tracefix.runtime.enforcement.engine import Runtime, run_protocol, run_ir, RunResult


# ---------------------------------------------------------------------------
# Minimal IR fixtures
# ---------------------------------------------------------------------------

# Two agents: A sends to B, B receives and terminates. No resources.
SIMPLE_IR = {
    "agents": [
        {"id": "A", "initial_state": "a_start"},
        {"id": "B", "initial_state": "b_start"},
    ],
    "resources": [],
    "channels": [
        {"id": "ch_ab", "from": "A", "to": "B", "labels": ["msg"]},
    ],
    "states": [
        {
            "id": "a_start", "agent": "A",
            "actions": [
                {"target": "a_done", "send": [{"channel": "ch_ab", "label": "msg"}]},
            ],
        },
        {"id": "a_done", "agent": "A", "actions": []},
        {
            "id": "b_start", "agent": "B",
            "actions": [
                {"target": "b_done", "receive": [{"channel": "ch_ab", "label": "msg"}]},
            ],
        },
        {"id": "b_done", "agent": "B", "actions": []},
    ],
}

# Single agent with a lock: acquire → release → done
LOCK_IR = {
    "agents": [
        {"id": "worker", "initial_state": "w_start"},
    ],
    "resources": [
        {"id": "my_lock", "type": "Lock"},
    ],
    "channels": [],
    "states": [
        {
            "id": "w_start", "agent": "worker",
            "actions": [
                {"target": "w_holding", "acquire": ["my_lock"]},
            ],
        },
        {
            "id": "w_holding", "agent": "worker",
            "actions": [
                {"target": "w_done", "release": ["my_lock"]},
            ],
        },
        {"id": "w_done", "agent": "worker", "actions": []},
    ],
}


# ---------------------------------------------------------------------------
# Helper: collect events from an EventBus
# ---------------------------------------------------------------------------

async def collect_events(bus: EventBus, count: int, timeout: float = 3.0) -> list[Event]:
    """Subscribe and collect up to `count` events."""
    collected = []
    q: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=256)
    bus._subscribers.add(q)
    try:
        deadline = asyncio.get_event_loop().time() + timeout
        while len(collected) < count:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            event = await asyncio.wait_for(q.get(), timeout=remaining)
            if event is None:
                break
            collected.append(event)
    except asyncio.TimeoutError:
        pass
    finally:
        bus._subscribers.discard(q)
    return collected


# ---------------------------------------------------------------------------
# EventBus unit tests
# ---------------------------------------------------------------------------

class TestEventBus:
    @pytest.mark.asyncio
    async def test_emit_and_subscribe(self):
        bus = EventBus()
        received = []

        async def listener():
            async for msg in bus.subscribe():
                received.append(msg)

        task = asyncio.create_task(listener())
        await asyncio.sleep(0.01)

        await bus.emit("test.event", {"key": "value"})
        await asyncio.sleep(0.01)

        await bus.close()
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(received) == 1
        assert "test.event" in received[0]
        assert '"key": "value"' in received[0]

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        bus = EventBus()
        results_1 = []
        results_2 = []

        async def listener(dest):
            async for msg in bus.subscribe():
                dest.append(msg)

        t1 = asyncio.create_task(listener(results_1))
        t2 = asyncio.create_task(listener(results_2))
        await asyncio.sleep(0.01)

        await bus.emit("ping", {"n": 1})
        await asyncio.sleep(0.01)
        await bus.close()
        await asyncio.sleep(0.01)

        for t in (t1, t2):
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

        assert len(results_1) == 1
        assert len(results_2) == 1

    @pytest.mark.asyncio
    async def test_sse_format(self):
        event = Event(type="step", data={"agent": "A"}, timestamp=1.0)
        sse = event.to_sse()
        assert sse.startswith("event: step\n")
        assert "data:" in sse
        assert '"agent": "A"' in sse
        assert sse.endswith("\n\n")


# ---------------------------------------------------------------------------
# Engine + EventBus integration tests
# ---------------------------------------------------------------------------

class TestEngineEvents:
    @pytest.mark.asyncio
    async def test_engine_emits_step_events(self):
        bus = EventBus()
        events = []

        async def collector():
            nonlocal events
            events = await collect_events(bus, count=20, timeout=5.0)

        collector_task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)

        result = await run_protocol(SIMPLE_IR, seed=42, timeout=5.0, event_bus=bus)
        await asyncio.sleep(0.1)
        await bus.close()
        await collector_task

        assert result.success

        step_events = [e for e in events if e.type == "step"]
        assert len(step_events) >= 2  # A sends, B receives → at least 2 steps

        # Verify step event data
        for se in step_events:
            assert "agent_id" in se.data
            assert "from_state" in se.data
            assert "to_state" in se.data
            assert "guards" in se.data
            assert "effects" in se.data

    @pytest.mark.asyncio
    async def test_engine_emits_run_start_done(self):
        bus = EventBus()
        events = []

        async def collector():
            nonlocal events
            events = await collect_events(bus, count=20, timeout=5.0)

        collector_task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)

        result = await run_protocol(SIMPLE_IR, seed=42, timeout=5.0, event_bus=bus)
        await asyncio.sleep(0.1)
        await bus.close()
        await collector_task

        assert result.success

        types = [e.type for e in events]
        assert "run.start" in types
        assert "run.done" in types

        # run.start should be first
        assert types[0] == "run.start"
        # run.done should be last
        assert types[-1] == "run.done"

        # Verify run.done data
        done_event = [e for e in events if e.type == "run.done"][0]
        assert done_event.data["success"] is True
        assert "steps" in done_event.data
        assert "duration" in done_event.data

    @pytest.mark.asyncio
    async def test_agent_done_event(self):
        bus = EventBus()
        events = []

        async def collector():
            nonlocal events
            events = await collect_events(bus, count=20, timeout=5.0)

        collector_task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)

        result = await run_protocol(SIMPLE_IR, seed=42, timeout=5.0, event_bus=bus)
        await asyncio.sleep(0.1)
        await bus.close()
        await collector_task

        assert result.success

        done_events = [e for e in events if e.type == "agent.done"]
        assert len(done_events) == 2  # A and B both terminate

        done_agents = {e.data["agent_id"] for e in done_events}
        assert done_agents == {"A", "B"}

        for de in done_events:
            assert "final_state" in de.data

    @pytest.mark.asyncio
    async def test_step_events_include_effects(self):
        """Verify that send/acquire/release effects appear in step events."""
        bus = EventBus()
        events = []

        async def collector():
            nonlocal events
            events = await collect_events(bus, count=20, timeout=5.0)

        collector_task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)

        result = await run_protocol(LOCK_IR, seed=42, timeout=5.0, event_bus=bus)
        await asyncio.sleep(0.1)
        await bus.close()
        await collector_task

        assert result.success

        step_events = [e for e in events if e.type == "step"]

        # First step: acquire lock
        acquire_step = next(
            (e for e in step_events if any("acquire" in g for g in e.data.get("guards", []))),
            None
        )
        assert acquire_step is not None

        # Second step: release lock
        release_step = next(
            (e for e in step_events if any("release" in eff for eff in e.data.get("effects", []))),
            None
        )
        assert release_step is not None


class TestNoEventsWithoutBus:
    def test_engine_works_without_event_bus(self):
        """Engine functions correctly when no event_bus is provided."""
        result = run_ir(SIMPLE_IR, seed=42, timeout=5.0)
        assert result.success
        assert result.steps >= 2

    def test_lock_ir_without_bus(self):
        result = run_ir(LOCK_IR, seed=42, timeout=5.0)
        assert result.success
        assert result.steps >= 2
