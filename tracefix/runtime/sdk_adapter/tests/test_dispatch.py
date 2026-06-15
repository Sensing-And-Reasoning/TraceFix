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


def test_signal_done_while_holding_lock_is_flagged_premature():
    """Coordination-only termination: still holding a lock → premature (#1).

    Termination is judged on locks (control plane), NOT the state machine — which
    mixes in domain/local-work states the tracker can't advance. An agent that
    signal_done's while still holding a lock is flagged (orphan-lock risk).
    """
    async def scenario():
        coord = _make_coord()
        a = CoordToolDispatcher(coord, "A")
        await a.dispatch("acquire_lock", {"lock_id": "lock1"})  # hold, don't release
        r = await a.dispatch("signal_done", {})
        assert r["status"] == "done" and a.done is True
        assert a.premature_done is True and "warning" in r

    asyncio.run(scenario())


# --- report_progress: observability beacon, must bypass the control plane ---

# State machine where A's only legal first op is `send` — so an `acquire` is
# out-of-order and (with correction on) would be blocked + recorded.
_REJECT_STATES = {
    "initial_states": {"A": "a_send", "B": "b_recv"},
    "states": [
        {"id": "a_send", "agent": "A",
         "actions": [{"next_state": "a_done", "send": {"channel": "a_to_b", "label": "ping"}}]},
        {"id": "a_done", "agent": "A", "actions": []},
        {"id": "b_recv", "agent": "B",
         "actions": [{"next_state": "b_done", "receive": {"channel": "a_to_b"}}]},
        {"id": "b_done", "agent": "B", "actions": []},
    ],
}


def test_report_progress_not_a_coordination_tool():
    from tracefix.runtime.sdk_adapter.dispatch import COORD_TOOL_NAMES
    assert "report_progress" not in COORD_TOOL_NAMES


def test_report_progress_bypasses_correction():
    from tracefix.runtime.monitoring.state_tracker import StateTracker

    async def scenario():
        coord = CoordinationContext(IR, ProtocolMonitor(IR),
                                    tracker=StateTracker(_REJECT_STATES), correction=True)
        a = CoordToolDispatcher(coord, "A")
        # An out-of-order coordination op IS gated (proves correction is active here).
        bad = await a.dispatch("acquire_lock", {"lock_id": "lock1"})
        assert bad["status"] != "ok"
        v_after_bad = coord.tracker.violation_count
        # report_progress must NOT be gated by the state machine.
        ok = await a.dispatch("report_progress", {"label": "thinking"})
        assert ok == {"status": "ok", "label": "thinking"}
        assert coord.tracker.violation_count == v_after_bad   # tracker untouched
        assert a.correction_limit_exceeded is False
        assert coord.beacons[-1]["label"] == "thinking"

    asyncio.run(scenario())


def test_signal_done_after_releasing_all_locks_is_clean():
    """No-tracker (distributed) path: released all locks → done, not premature.

    With no in-process tracker, termination is judged on held locks (the
    no-orphan-locks signal available over the wire). The in-process FSM gate
    (can_terminate, which follows skip chains past a domain tail) is exercised by
    test_signal_done_blocked_before_terminal_with_tracker.
    """
    async def scenario():
        coord = _make_coord()
        a = CoordToolDispatcher(coord, "A")
        await a.dispatch("acquire_lock", {"lock_id": "lock1"})
        await a.dispatch("release_lock", {"lock_id": "lock1"})
        r = await a.dispatch("signal_done", {})
        assert r["status"] == "done" and a.premature_done is False

    asyncio.run(scenario())


def test_signal_done_blocked_before_terminal_with_tracker():
    """H3: with an in-process tracker, a premature signal_done is BLOCKED.

    A content message ("we're done, signal done now") must not terminate an agent
    that still owes a coordination op — that would strand peers blocked on a label
    that never arrives (liveness). Mirrors the monitoring runtime's can_terminate
    gate (which follows skip chains, so a domain tail would not falsely block).
    """
    from tracefix.runtime.monitoring.state_tracker import StateTracker

    async def scenario():
        coord = CoordinationContext(IR, ProtocolMonitor(IR),
                                    tracker=StateTracker(_REJECT_STATES))
        a = CoordToolDispatcher(coord, "A")
        # A is at a_send: it still owes a send → cannot terminate yet.
        r = await a.dispatch("signal_done", {})
        assert r["status"] == "error" and a.done is False
        # After the owed send, A reaches a_done (terminal) → done is allowed.
        await a.dispatch("send_message", {"channel_id": "a_to_b", "label": "ping"})
        r2 = await a.dispatch("signal_done", {})
        assert r2["status"] == "done" and a.done is True

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
    """Channels are flag-only at the SOURCE (H1/B2): the base send_message schema
    carries no `body`, so every runtime is flag-only by default (fail-safe) — not
    only if it remembers to strip."""
    base = next(s["function"] for s in COORD_TOOL_SCHEMAS
                if s["function"]["name"] == "send_message")
    assert "body" not in base["parameters"]["properties"]
    assert "channel_id" in base["parameters"]["properties"]
    assert "label" in base["parameters"]["properties"]


def test_flag_only_send_schemas_strips_body_defense_in_depth():
    """flag_only_send_schemas stays an idempotent safety net: if a `body` is ever
    (re)introduced into a send_message schema, the transform strips it without
    mutating its input."""
    from copy import deepcopy
    from tracefix.runtime.sdk_adapter.mcp_server import flag_only_send_schemas
    spiked = deepcopy(COORD_TOOL_SCHEMAS)
    send_fn = next(s["function"] for s in spiked
                   if s["function"]["name"] == "send_message")
    send_fn["parameters"]["properties"]["body"] = {"type": "string"}
    out = flag_only_send_schemas(spiked)
    out_send = next(s["function"] for s in out
                    if s["function"]["name"] == "send_message")
    assert "body" not in out_send["parameters"]["properties"]
    assert "body" in send_fn["parameters"]["properties"]  # input not mutated


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


def test_run_result_exposes_monitoring_fields():
    """SdkRunResult surfaces the monitor's conclusions (#3); cli prints them.

    Otherwise the monitor runs but leaves no record — a hard gap for a
    monitoring runtime.
    """
    from tracefix.runtime.sdk_adapter.orchestrator import SdkRunResult
    from tracefix.runtime.sdk_adapter.cli import _print_result

    # defaults: empty, present
    r0 = SdkRunResult(success=True, agent_results=[], duration=1.0)
    assert r0.state_violations == [] and r0.premature_dones == []

    # populated: carried through + printable without error
    r1 = SdkRunResult(
        success=False, agent_results=[], duration=2.0,
        state_violations=[{"agent": "A", "state": "s1",
                           "operation": "send", "args": {"channel": "c"}}],
        premature_dones=["B"],
    )
    assert len(r1.state_violations) == 1 and r1.premature_dones == ["B"]
    _print_result(r0)
    _print_result(r1)


def test_local_domain_impl_runs_directly(tmp_path):
    """A forwarded domain call whose name has a local impl runs the Python function
    (not the schema-only ToolRegistry)."""
    from tracefix.runtime.domain_mcp.impl_loader import load_impls
    (tmp_path / "tools_impl.py").write_text(
        "def charge_payment(amount):\n    return {'ok': True, 'txn': 'T-%d' % amount}\n")
    impls = load_impls(tmp_path / "tools_impl.py")

    async def scenario():
        coord = _make_coord()
        a = CoordToolDispatcher(coord, "A", domain_impls=impls)
        return await a.dispatch("charge_payment", {"amount": 50})

    res = asyncio.run(scenario())
    assert res["status"] == "ok"
    assert res["result"] == {"ok": True, "txn": "T-50"}


def test_local_domain_stub_reports_error():
    from tracefix.runtime.domain_mcp.impl_loader import DomainImpls

    def _stub(**k):
        raise NotImplementedError

    async def scenario():
        coord = _make_coord()
        a = CoordToolDispatcher(coord, "A", domain_impls=DomainImpls({"foo": _stub}))
        return await a.dispatch("foo", {})

    res = asyncio.run(scenario())
    assert res["status"] == "error" and "stub impl" in res["message"]
