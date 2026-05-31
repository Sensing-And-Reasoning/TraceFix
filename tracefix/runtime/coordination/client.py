"""CoordClient: the remote CoordBackend used by an agent node.

Implements the same 6 methods + ``get_held_locks`` as the in-process
``CoordinationContext``, but each call becomes one HTTP ``POST /rpc`` to a
``CoordinationService`` and returns the response dict. Blocking is transparent:
the RPC simply doesn't return until the service returns acquired/received/timeout.
The socket read timeout is set above the coordination op timeout so the client
never gives up before the service answers.
"""

from __future__ import annotations

import asyncio
import json
from urllib.parse import urlparse

from tracefix.runtime.coordination.backend import DEFAULT_TIMEOUT

# Extra slack added to a blocking op's timeout for the socket read deadline, so the
# client always waits a bit longer than the server's own timeout.
_SOCKET_SLACK = 15.0


class CoordClient:
    """Network client implementing CoordBackend against a CoordinationService."""

    def __init__(self, server_url: str, agent_id: str, *,
                 socket_timeout: float | None = None):
        u = urlparse(server_url if "://" in server_url else f"http://{server_url}")
        self.host = u.hostname or "127.0.0.1"
        self.port = u.port or 8780
        self.agent_id = agent_id              # this node's agent (bound, like the dispatcher)
        self.socket_timeout = socket_timeout  # override; else op_timeout + slack

    async def _rpc(self, method: str, args: dict, *,
                   op_timeout: float = DEFAULT_TIMEOUT) -> dict | list:
        payload = json.dumps({"method": method, "args": args}).encode("utf-8")
        request = (
            f"POST /rpc HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode() + payload
        read_timeout = self.socket_timeout or (op_timeout + _SOCKET_SLACK)
        return await self._http_roundtrip(request, read_timeout)

    async def _http_roundtrip(self, request: bytes, read_timeout: float):
        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            writer.write(request)
            await writer.drain()
            await asyncio.wait_for(reader.readline(), timeout=read_timeout)  # status line
            content_length = 0
            while True:
                header = await asyncio.wait_for(reader.readline(), timeout=read_timeout)
                if header in (b"\r\n", b"\n", b""):
                    break
                h = header.decode("utf-8", "replace")
                if h.lower().startswith("content-length:"):
                    content_length = int(h.split(":", 1)[1].strip())
            if content_length <= 0:
                return {}
            body = await asyncio.wait_for(
                reader.readexactly(content_length), timeout=read_timeout)
            return json.loads(body.decode("utf-8"))
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    # --- CoordBackend interface ---

    async def acquire_lock(self, resource_id: str, agent_id: str,
                           timeout: float = DEFAULT_TIMEOUT) -> dict:
        return await self._rpc("acquire_lock",
                               {"resource_id": resource_id, "agent_id": agent_id,
                                "timeout": timeout}, op_timeout=timeout)

    async def release_lock(self, resource_id: str, agent_id: str) -> dict:
        return await self._rpc("release_lock",
                               {"resource_id": resource_id, "agent_id": agent_id})

    async def send(self, channel_id: str, label: str, agent_id: str,
                   body: str = "") -> dict:
        return await self._rpc("send",
                               {"channel_id": channel_id, "label": label,
                                "agent_id": agent_id, "body": body})

    async def receive(self, channel_id: str, agent_id: str,
                      timeout: float = DEFAULT_TIMEOUT) -> dict:
        return await self._rpc("receive",
                               {"channel_id": channel_id, "agent_id": agent_id,
                                "timeout": timeout}, op_timeout=timeout)

    async def poll_channels(self, channel_ids: list[str], agent_id: str) -> dict:
        return await self._rpc("poll_channels",
                               {"channel_ids": channel_ids, "agent_id": agent_id})

    async def receive_any(self, channel_ids: list[str], agent_id: str,
                          timeout: float = DEFAULT_TIMEOUT) -> dict:
        return await self._rpc("receive_any",
                               {"channel_ids": channel_ids, "agent_id": agent_id,
                                "timeout": timeout}, op_timeout=timeout)

    async def get_held_locks(self, agent_id: str) -> list[str]:
        result = await self._rpc("get_held_locks", {"agent_id": agent_id})
        return result if isinstance(result, list) else []

    # --- orchestrator helper (not part of CoordBackend) ---

    async def fetch_monitoring(self) -> dict:
        """GET /monitoring — the service's tracker conclusions (state_violations, ...)."""
        request = (
            f"GET /monitoring HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode()
        result = await self._http_roundtrip(request, read_timeout=10.0)
        return result if isinstance(result, dict) else {}
