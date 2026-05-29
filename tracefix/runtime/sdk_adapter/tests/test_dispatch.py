"""SDK-free tests for the coordination tool dispatcher.

These exercise ``CoordToolDispatcher`` against a real ``CoordinationContext`` +
``ProtocolMonitor`` — no Claude Agent SDK install or API access required. They
prove the adapter's coordination core (the part that matters for verification
fidelity) is wired correctly onto the existing tracefix layer.
"""

from __future__ import annotations

import asyncio

from tracefix.runtime.monitoring.coord import CoordinationContext
from tracefix.runtime.monitoring.monitor import ProtocolMonitor
from tracefix.runtime.sdk_adapter.dispatch import CoordToolDispatcher
from tracefix.runtime.sdk_adapter.mcp_server import (
    allowed_tool_names, _openai_schema_to_sdk,
)
from tracefix.runtime.monitoring.coord import COORD_TOOL_SCHEMAS

# Minimal two-agent IR: A → B over channel a_to_b, plus one shared lock.
IR = {
    "agents": [{"id": "A"}, {"id": "B"}],
    "resources": [{"id": "lock1", "type": "Lock"},
                  {"id": "pool", "type": "Counter", "initial_value": 1}],
    "channels": [{"id": "a_to_b", "from": "A", "to": "B", "labels": ["ping"]}],
}


def _make_coord() -> CoordinationContext:
    return CoordinationContext(IR, ProtocolMonitor(IR))


def test_acquire_send_receive_happy_path():
    async def scenario():
        coord = _make_coord()
        a = CoordToolDispatcher(coord, "A")
        b = CoordToolDispatcher(coord, "B")

        r = await a.dispatch("acquire_lock", {"lock_id": "lock1"})
        assert r["status"] == "acquired" and r["lock"] == "lock1"

        r = await a.dispatch("send_message", {"channel_id": "a_to_b", "label": "ping"})
        assert r["status"] == "sent" and r["label"] == "ping"

        r = await b.dispatch("receive_message", {"channel_id": "a_to_b"})
        assert r["status"] == "received" and r["label"] == "ping"

        r = await a.dispatch("release_lock", {"lock_id": "lock1"})
        assert r["status"] == "released"

        # Trace recorded for each call (round-numbered).
        assert [tc.round for tc in a.trace] == [1, 2, 3]
        assert a.trace[0].tool_name == "acquire_lock"

    asyncio.run(scenario())


def test_counter_resource_roundtrip():
    async def scenario():
        coord = _make_coord()
        a = CoordToolDispatcher(coord, "A")
        r = await a.dispatch("acquire_lock", {"lock_id": "pool"})
        assert r["status"] == "acquired" and r["remaining"] == 0
        r = await a.dispatch("release_lock", {"lock_id": "pool"})
        assert r["status"] == "released" and r["remaining"] == 1

    asyncio.run(scenario())


def test_protocol_violation_maps_to_error():
    async def scenario():
        coord = _make_coord()
        # B is NOT allowed to send on a_to_b (channel is A->B); monitor must reject.
        b = CoordToolDispatcher(coord, "B")
        r = await b.dispatch("send_message", {"channel_id": "a_to_b", "label": "ping"})
        assert r["status"] == "error"
        assert "violation" in r["message"].lower()

    asyncio.run(scenario())


def test_signal_done_without_tracker_is_allowed():
    async def scenario():
        coord = _make_coord()  # no states.json → tracker is None
        a = CoordToolDispatcher(coord, "A")
        r = await a.dispatch("signal_done", {})
        assert r["status"] == "done"
        assert a.done is True

    asyncio.run(scenario())


def test_signal_done_premature_is_accepted_with_warning():
    """Tracker can't confirm terminal state → accept anyway, flag premature.

    Regression for the 1E run where agents finished all coordination but the
    tracker (which only advances on coord ops) couldn't reach a terminal state
    through domain-tool tail transitions — a hard gate would deadlock them.
    """
    async def scenario():
        coord = _make_coord()

        class FakeTracker:
            def can_terminate(self, agent_id):
                return False

        coord.tracker = FakeTracker()
        a = CoordToolDispatcher(coord, "A")
        r = await a.dispatch("signal_done", {})
        assert r["status"] == "done"
        assert "warning" in r
        assert a.done is True and a.premature_done is True

    asyncio.run(scenario())


def test_domain_tool_strips_duplicate_agent_id():
    """LLM-supplied agent_id in args must not collide with the bound agent_id.

    Regression for the 1E run where an agent passed agent_id explicitly, causing
    ToolRegistry.call(agent_id=..., agent_id=...) to TypeError.
    """
    async def scenario():
        coord = _make_coord()
        seen = {}

        class FakeResult:
            success = True
            def to_dict(self):
                return {"ok": True}

        class FakeRegistry:
            async def call(self, name, agent_id=None, **kwargs):
                seen["agent_id"] = agent_id
                seen["kwargs"] = kwargs
                return FakeResult()

        a = CoordToolDispatcher(coord, "A", tool_registry=FakeRegistry())
        r = await a.dispatch("design_feature", {"feature_name": "x", "agent_id": "A"})
        assert r["status"] == "ok"
        assert seen["agent_id"] == "A"
        assert "agent_id" not in seen["kwargs"]
        assert seen["kwargs"] == {"feature_name": "x"}

    asyncio.run(scenario())


def test_unknown_tool_without_registry_errors():
    async def scenario():
        coord = _make_coord()
        a = CoordToolDispatcher(coord, "A")
        r = await a.dispatch("write_section", {"section": "intro"})
        assert r["status"] == "error" and "Unknown tool" in r["message"]

    asyncio.run(scenario())


def test_missing_required_arg_errors():
    async def scenario():
        coord = _make_coord()
        a = CoordToolDispatcher(coord, "A")
        r = await a.dispatch("acquire_lock", {})  # missing lock_id
        assert r["status"] == "error" and "argument" in r["message"].lower()

    asyncio.run(scenario())


# -- schema conversion (also SDK-free) --------------------------------------

def test_send_message_schema_is_flag_only():
    """flag_only_send_schemas removes `body` (control plane = label only)."""
    from tracefix.runtime.sdk_adapter.mcp_server import flag_only_send_schemas
    schemas = flag_only_send_schemas(COORD_TOOL_SCHEMAS)
    send = next(s["function"] for s in schemas
                if s["function"]["name"] == "send_message")
    assert "body" not in send["parameters"]["properties"]
    assert "channel_id" in send["parameters"]["properties"]
    assert "label" in send["parameters"]["properties"]
    # Original schemas must be untouched (deepcopy, not mutate).
    orig = next(s["function"] for s in COORD_TOOL_SCHEMAS
                if s["function"]["name"] == "send_message")
    assert "body" in orig["parameters"]["properties"]


def test_send_drops_body_so_no_payload_crosses_channel():
    """Even if an agent attaches a body, it never crosses the channel.

    Regression for the 3E run where the EDITOR put domain feedback into the
    message body. The control plane must carry only the label.
    """
    async def scenario():
        coord = _make_coord()
        a = CoordToolDispatcher(coord, "A")
        r = await a.dispatch("send_message", {
            "channel_id": "a_to_b", "label": "ping", "body": "SECRET PAYLOAD"})
        assert r["status"] == "sent"
        assert "note" in r  # body was ignored and flagged

        b = CoordToolDispatcher(coord, "B")
        rb = await b.dispatch("receive_message", {"channel_id": "a_to_b"})
        assert rb["status"] == "received" and rb["label"] == "ping"
        assert "body" not in rb  # no payload crossed the channel

    asyncio.run(scenario())


def test_schema_conversion_and_allowed_names():
    # Every coordination schema converts to (name, desc, json_schema).
    for schema in COORD_TOOL_SCHEMAS:
        name, desc, params = _openai_schema_to_sdk(schema["function"])
        assert isinstance(name, str) and name
        assert isinstance(params, dict) and params.get("type") == "object"

    names = allowed_tool_names(COORD_TOOL_SCHEMAS, "tracefix")
    assert "mcp__tracefix__acquire_lock" in names
    assert "mcp__tracefix__signal_done" in names
    assert len(names) == len(COORD_TOOL_SCHEMAS)
