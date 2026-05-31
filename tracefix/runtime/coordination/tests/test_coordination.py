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
