"""Loopback integration tests for the distributed coordination layer.

SDK-free / API-free: starts a real ``CoordinationService`` (wrapping a real
``CoordinationContext``) on a loopback port and drives it with ``CoordClient``s.
This exercises the actual network path — the seam that makes the MAS multi-node —
including the crux: a cross-network lock block-and-wake (B blocks on a lock A
holds, over the socket, and wakes when A releases).
"""

from __future__ import annotations

import asyncio
import socket

from tracefix.runtime.monitoring.coord import CoordinationContext
from tracefix.runtime.monitoring.monitor import ProtocolMonitor
from tracefix.runtime.coordination.service import CoordinationService
from tracefix.runtime.coordination.client import CoordClient

IR = {
    "agents": [{"id": "A"}, {"id": "B"}],
    "resources": [{"id": "lock1", "type": "Lock"}],
    "channels": [{"id": "a_to_b", "from": "A", "to": "B", "labels": ["ping"]}],
}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _start_service(port: int) -> CoordinationService:
    coord = CoordinationContext(IR, ProtocolMonitor(IR))
    svc = CoordinationService(coord, host="127.0.0.1", port=port)
    await svc.start()
    return svc


def test_remote_send_receive():
    async def scenario():
        port = _free_port()
        svc = await _start_service(port)
        try:
            url = f"http://127.0.0.1:{port}"
            a, b = CoordClient(url, "A"), CoordClient(url, "B")
            r = await a.send("a_to_b", "ping", "A")
            assert r["status"] == "sent" and r["label"] == "ping"
            r = await b.receive("a_to_b", "B", timeout=5)
            assert r["status"] == "received" and r["label"] == "ping"
        finally:
            await svc.stop()

    asyncio.run(scenario())


def test_remote_lock_contention_block_and_wake():
    """A acquires; B blocks over the network; A releases; B wakes and acquires."""
    async def scenario():
        port = _free_port()
        svc = await _start_service(port)
        try:
            url = f"http://127.0.0.1:{port}"
            a, b = CoordClient(url, "A"), CoordClient(url, "B")
            r = await a.acquire_lock("lock1", "A")
            assert r["status"] == "acquired"

            b_task = asyncio.create_task(b.acquire_lock("lock1", "B", timeout=5))
            await asyncio.sleep(0.4)  # give B time to block server-side
            assert not b_task.done()  # B is genuinely blocked across the socket

            r = await a.release_lock("lock1", "A")
            assert r["status"] == "released"

            rb = await b_task  # the release woke B's parked RPC
            assert rb["status"] == "acquired"
        finally:
            await svc.stop()

    asyncio.run(scenario())


def test_remote_get_held_locks():
    async def scenario():
        port = _free_port()
        svc = await _start_service(port)
        try:
            url = f"http://127.0.0.1:{port}"
            a = CoordClient(url, "A")
            await a.acquire_lock("lock1", "A")
            assert await a.get_held_locks("A") == ["lock1"]
            await a.release_lock("lock1", "A")
            assert await a.get_held_locks("A") == []
        finally:
            await svc.stop()

    asyncio.run(scenario())


def test_remote_monitor_rejects_illegal_send():
    """The authority's ProtocolMonitor validates over the network too."""
    async def scenario():
        port = _free_port()
        svc = await _start_service(port)
        try:
            url = f"http://127.0.0.1:{port}"
            b = CoordClient(url, "B")  # B may NOT send on a_to_b (channel is A->B)
            r = await b.send("a_to_b", "ping", "B")
            assert r["status"] == "error" and "violation" in r["message"].lower()
        finally:
            await svc.stop()

    asyncio.run(scenario())


def test_remote_receive_timeout():
    async def scenario():
        port = _free_port()
        svc = await _start_service(port)
        try:
            url = f"http://127.0.0.1:{port}"
            b = CoordClient(url, "B")
            r = await b.receive("a_to_b", "B", timeout=1)  # nothing sent
            assert r["status"] == "timeout"
        finally:
            await svc.stop()

    asyncio.run(scenario())


# --- Observability plane over the network: report_progress + monitoring snapshot ---

_PHASE_STATES = {
    "initial_states": {"A": "a_acquire"},
    "states": [
        {"id": "a_acquire", "agent": "A",
         "actions": [{"next_state": "a_write", "acquire": "lock1"}]},
        {"id": "a_write", "agent": "A", "task": "do the work",
         "actions": [{"next_state": "a_release"}]},
        {"id": "a_release", "agent": "A",
         "actions": [{"next_state": "a_done", "release": "lock1"}]},
        {"id": "a_done", "agent": "A", "actions": []},
    ],
}


def test_rpc_methods_includes_report_progress():
    from tracefix.runtime.coordination.service import _RPC_METHODS
    assert "report_progress" in _RPC_METHODS


# --- H3 termination gate over the network (distributed parity) ---

async def _start_service_tracked(port: int) -> CoordinationService:
    """A service whose CoordinationContext has a StateTracker, so signal_done can
    be FSM-gated server-side (the parity the opencode harness needs)."""
    from tracefix.runtime.monitoring.state_tracker import StateTracker
    coord = CoordinationContext(IR, ProtocolMonitor(IR),
                                tracker=StateTracker(_PHASE_STATES))
    svc = CoordinationService(coord, host="127.0.0.1", port=port)
    await svc.start()
    return svc


def test_rpc_methods_includes_signal_done():
    from tracefix.runtime.coordination.service import _RPC_METHODS
    assert "signal_done" in _RPC_METHODS


def test_remote_signal_done_gated_by_server_side_fsm():
    """H3 over the wire: a premature signal_done is rejected by the AUTHORITATIVE
    server-side tracker (the full FSM gate), not just a held-locks fallback. This is
    the distributed parity that opencode (always) and sdk --coord-url now get."""
    async def scenario():
        port = _free_port()
        svc = await _start_service_tracked(port)
        try:
            a = CoordClient(f"http://127.0.0.1:{port}", "A")
            # A is at a_acquire — it still owes acquire+release → cannot terminate.
            r = await a.signal_done("A")
            assert r["status"] == "error" and r.get("error") == "cannot_terminate"
            # Complete the protocol; A reaches a_done (terminal).
            assert (await a.acquire_lock("lock1", "A"))["status"] == "acquired"
            assert (await a.release_lock("lock1", "A"))["status"] == "released"
            r2 = await a.signal_done("A")
            assert r2["status"] == "done"
        finally:
            await svc.stop()

    asyncio.run(scenario())


# --- Data plane over the network (claim-check across nodes) ---

def test_rpc_methods_includes_data_plane():
    from tracefix.runtime.coordination.service import _RPC_METHODS
    assert {"post_content", "get_content"} <= _RPC_METHODS


def test_remote_data_plane_post_get_across_agents():
    """H4: content posted by one node resolves via get_content on ANOTHER — the
    claim-check store is server-side, so a ref works over the wire (the content
    exchange the default opencode harness needs)."""
    async def scenario():
        port = _free_port()
        svc = await _start_service(port)
        try:
            url = f"http://127.0.0.1:{port}"
            a, b = CoordClient(url, "A"), CoordClient(url, "B")
            posted = await a.post_content("revision notes", "A")
            assert posted["status"] == "ok" and posted["ref"]
            got = await b.get_content(posted["ref"], "B")
            assert got["status"] == "ok" and got["content"] == "revision notes"
        finally:
            await svc.stop()

    asyncio.run(scenario())


# --- Capability tokens: an agent can't forge RPCs as a peer (H4) ---

async def _start_service_with_tokens(port: int, tokens: dict) -> CoordinationService:
    coord = CoordinationContext(IR, ProtocolMonitor(IR))
    svc = CoordinationService(coord, host="127.0.0.1", port=port, tokens=tokens)
    await svc.start()
    return svc


def test_token_binding_rejects_forgery_and_anon():
    """With tokens configured, an RPC must carry the token bound to the agent_id it
    acts as. The correct token works; A's token claiming to be B is rejected; and a
    tokenless call is rejected."""
    async def scenario():
        port = _free_port()
        svc = await _start_service_with_tokens(port, {"A": "tokA", "B": "tokB"})
        try:
            url = f"http://127.0.0.1:{port}"
            ok = await CoordClient(url, "A", token="tokA").acquire_lock("lock1", "A")
            assert ok["status"] == "acquired"
            # A's token but claiming to be B → forgery, rejected.
            forge = await CoordClient(url, "B", token="tokA").acquire_lock("lock1", "B")
            assert forge.get("error") == "unauthorized"
            # No token at all → rejected.
            anon = await CoordClient(url, "A").release_lock("lock1", "A")
            assert anon.get("error") == "unauthorized"
        finally:
            await svc.stop()

    asyncio.run(scenario())


def test_no_tokens_configured_is_open():
    """Backward-compatible: a service started without tokens accepts any caller
    (in-process / trusted-loopback callers like mixed_run)."""
    async def scenario():
        port = _free_port()
        svc = await _start_service(port)  # tokens=None
        try:
            r = await CoordClient(f"http://127.0.0.1:{port}", "A").acquire_lock("lock1", "A")
            assert r["status"] == "acquired"
        finally:
            await svc.stop()

    asyncio.run(scenario())


def test_remote_report_progress_roundtrip():
    async def scenario():
        port = _free_port()
        svc = await _start_service(port)
        try:
            a = CoordClient(f"http://127.0.0.1:{port}", "A")
            r = await a.report_progress("generating", "A")
            assert r == {"status": "ok", "label": "generating"}
            assert len(svc.coord.beacons) == 1
            assert svc.coord.beacons[0]["label"] == "generating"
        finally:
            await svc.stop()

    asyncio.run(scenario())


def test_dispatch_report_progress_via_service():
    import json
    from tracefix.runtime.monitoring.coord import CoordinationContext
    from tracefix.runtime.monitoring.monitor import ProtocolMonitor

    async def scenario():
        coord = CoordinationContext(IR, ProtocolMonitor(IR))
        svc = CoordinationService(coord, host="127.0.0.1", port=_free_port())
        body = json.dumps({"method": "report_progress",
                           "args": {"label": "x", "agent_id": "A"}}).encode()
        out = json.loads(await svc._dispatch(body))
        assert out == {"status": "ok", "label": "x"}
        assert coord.beacons[-1]["label"] == "x"

    asyncio.run(scenario())


def test_monitoring_snapshot_has_phases_and_beacons():
    import json
    from tracefix.runtime.monitoring.coord import CoordinationContext
    from tracefix.runtime.monitoring.monitor import ProtocolMonitor
    from tracefix.runtime.monitoring.state_tracker import StateTracker

    async def scenario():
        coord = CoordinationContext(IR, ProtocolMonitor(IR),
                                    tracker=StateTracker(_PHASE_STATES))
        await coord.acquire_lock("lock1", "A")        # → business phase a_write
        await coord.report_progress("sub-step", "A")  # → a beacon
        svc = CoordinationService(coord, host="127.0.0.1", port=_free_port())
        snap = json.loads(svc._monitoring_snapshot().decode())
        assert snap["current_phases"]["A"] == "a_write"
        assert snap["state_tasks"]["a_write"] == "do the work"
        assert any(bk["label"] == "sub-step" for bk in snap["beacons"])

    asyncio.run(scenario())
