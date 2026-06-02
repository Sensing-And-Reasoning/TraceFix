"""Live-visualization wiring for the SDK adapter (SDK-free / API-free).

Proves the new plumbing: a ``CoordToolDispatcher`` and the
``CoordinationContext`` it talks to, when given an ``EventBus``, emit
``agent.tool_call`` + ``state.transition`` events that flow through the real
``live_server`` to a connected SSE client — i.e. ``sdk_adapter run --live``
will actually stream to the browser.
"""

from __future__ import annotations

import asyncio
import socket

from tracefix.runtime.monitoring.monitor import ProtocolMonitor
from tracefix.runtime.monitoring.state_tracker import StateTracker
from tracefix.runtime.monitoring.coord import CoordinationContext
from tracefix.runtime.monitoring.event_bus import EventBus
from tracefix.runtime.monitoring.live_server import start_live_server
from tracefix.runtime.sdk_adapter.dispatch import CoordToolDispatcher

IR = {
    "agents": [{"id": "WRITER"}, {"id": "APPROVER"}],
    "resources": [{"id": "DOC", "type": "Lock"}],
    "channels": [{"id": "w2a", "from": "WRITER", "to": "APPROVER", "labels": ["drafted"]}],
}
STATES = {
    "states": [
        {"id": "WRITER_acq", "agent": "WRITER",
         "actions": [{"acquire": "DOC", "next_state": "WRITER_done"}]},
        {"id": "WRITER_done", "agent": "WRITER", "actions": []},
        {"id": "APPROVER_wait", "agent": "APPROVER",
         "actions": [{"receive": {"channel": "w2a"}, "next_state": "APPROVER_done"}]},
        {"id": "APPROVER_done", "agent": "APPROVER", "actions": []},
    ],
    "initial_states": {"WRITER": "WRITER_acq", "APPROVER": "APPROVER_wait"},
}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_sdk_dispatcher_events_reach_live_server():
    async def scenario():
        bus = EventBus()
        port = _free_port()
        coord = CoordinationContext(IR, ProtocolMonitor(IR),
                                    tracker=StateTracker(STATES),
                                    correction=True, event_bus=bus)
        disp = CoordToolDispatcher(coord, "WRITER", event_bus=bus)
        server = await start_live_server(IR, bus, port=port, title="t", model="m")
        try:
            # connect an SSE client FIRST so it is subscribed before we emit
            r, w = await asyncio.open_connection("127.0.0.1", port)
            w.write(b"GET /api/events HTTP/1.1\r\nHost: x\r\n\r\n")
            await w.drain()
            await asyncio.sleep(0.2)

            # one legal coordination op via the SDK dispatcher
            res = await disp.dispatch("acquire_lock", {"lock_id": "DOC"})
            assert res["status"] == "acquired"
            await asyncio.sleep(0.3)

            try:
                data = await asyncio.wait_for(r.read(8000), timeout=2)
            except asyncio.TimeoutError:
                data = b""
            txt = data.decode("utf-8", "replace")
            # the dispatcher's tool-call event AND the coord's state transition
            assert "agent.tool_call" in txt, txt[:200]
            assert "state.transition" in txt, txt[:200]
            w.close()
        finally:
            server.close()  # non-blocking; avoids wait_closed() on the open SSE socket

    asyncio.run(scenario())
