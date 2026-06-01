"""CoordinationService: the authority node.

Wraps an UNCHANGED ``CoordinationContext`` (coord.py + store.py + monitor.py +
state_tracker.py, all reused verbatim) and serves the 6 coordination methods +
``get_held_locks`` over HTTP ``POST /rpc``. Blocking lives here: a blocked
``receive``/``acquire_lock`` is a request whose HTTP response simply hasn't been
written yet; when another node's ``send``/``release`` fires the server-side
``asyncio.Condition``, the parked coroutine wakes and the response is sent.

HTTP handling copies the zero-dependency raw-asyncio pattern from
``monitoring/live_server.py`` and adds POST-body reading.
"""

from __future__ import annotations

import asyncio
import json
import sys

from tracefix.runtime.monitoring.monitor import ProtocolViolation, StateGuidanceError

# Methods on CoordinationContext exposed over RPC (the CoordBackend surface).
_RPC_METHODS = frozenset({
    "acquire_lock", "release_lock", "send", "receive",
    "poll_channels", "receive_any", "get_held_locks",
})


def _http_response(status: int, content_type: str, body: bytes) -> bytes:
    reason = {200: "OK", 400: "Bad Request", 404: "Not Found",
              500: "Internal Server Error"}.get(status, "OK")
    headers = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    return headers.encode() + body


async def _read_request(reader: asyncio.StreamReader):
    """Parse request line + headers + (optional) body. Returns (method, path, body)."""
    request_line = await reader.readline()
    if not request_line:
        return None, None, b""
    parts = request_line.decode("utf-8", "replace").strip().split(" ")
    method = parts[0] if parts else "GET"
    path = parts[1] if len(parts) > 1 else "/"

    content_length = 0
    while True:
        header = await reader.readline()
        if header in (b"\r\n", b"\n", b""):
            break
        h = header.decode("utf-8", "replace")
        if h.lower().startswith("content-length:"):
            try:
                content_length = int(h.split(":", 1)[1].strip())
            except ValueError:
                content_length = 0

    body = await reader.readexactly(content_length) if content_length > 0 else b""
    return method, path, body


class CoordinationService:
    """Serves an in-process CoordinationContext to remote agent nodes over HTTP."""

    def __init__(self, coord, host: str = "127.0.0.1", port: int = 8780,
                 verbose: bool = False):
        self.coord = coord          # an unchanged CoordinationContext
        self.host = host
        self.port = port
        self.verbose = verbose
        self._server: asyncio.Server | None = None

    async def _handle(self, reader: asyncio.StreamReader,
                      writer: asyncio.StreamWriter):
        try:
            method, path, body = await _read_request(reader)
            if method is None:
                return
            if method == "GET" and path == "/health":
                writer.write(_http_response(200, "application/json", b'{"status":"ok"}'))
                await writer.drain()
            elif method == "GET" and path == "/monitoring":
                writer.write(_http_response(200, "application/json",
                                            self._monitoring_snapshot()))
                await writer.drain()
            elif method == "POST" and path == "/rpc":
                writer.write(_http_response(200, "application/json",
                                            await self._dispatch(body)))
                await writer.drain()
            else:
                writer.write(_http_response(404, "text/plain", b"Not Found"))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:  # noqa: BLE001
            try:
                err = json.dumps({"status": "error",
                                  "message": f"{type(e).__name__}: {e}"}).encode()
                writer.write(_http_response(500, "application/json", err))
                await writer.drain()
            except Exception:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch(self, body: bytes) -> bytes:
        try:
            req = json.loads(body.decode("utf-8"))
            name = req["method"]
            args = req.get("args", {})
        except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as e:
            return json.dumps({"status": "error",
                               "message": f"bad request: {e}"}).encode()
        if name not in _RPC_METHODS:
            return json.dumps({"status": "error",
                               "message": f"unknown method: {name}"}).encode()
        fn = getattr(self.coord, name)
        try:
            result = await fn(**args)
        except StateGuidanceError as e:  # subclass — must precede ProtocolViolation
            result = {"status": "error", "error": "out_of_order",
                      "message": str(e), "legal_actions": e.legal_actions,
                      "hint": e.context}
        except ProtocolViolation as e:
            result = {"status": "error", "message": f"Protocol violation: {e}"}
        except Exception as e:  # noqa: BLE001
            result = {"status": "error", "message": f"{type(e).__name__}: {e}"}
        if self.verbose:
            print(f"[coord] {name}({args}) -> {result}", file=sys.stderr)
        return json.dumps(result).encode()

    def _monitoring_snapshot(self) -> bytes:
        """Expose the monitor's conclusions so a remote orchestrator can collect them
        (the distributed analogue of SdkRunResult.state_violations)."""
        tracker = getattr(self.coord, "tracker", None)
        violations = []
        current_states = {}
        if tracker is not None:
            for v in tracker.violations:
                violations.append({
                    "agent": getattr(v, "agent", None),
                    "state": getattr(v, "current_state", None),
                    "operation": getattr(v, "operation", None),
                    "args": getattr(v, "args", None),
                })
            current_states = dict(tracker.current_states)
        return json.dumps({"state_violations": violations,
                           "current_states": current_states}).encode()

    async def start(self) -> asyncio.Server:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        return self._server

    async def serve_forever(self):
        if self._server is None:
            await self.start()
        async with self._server:
            await self._server.serve_forever()

    async def stop(self):
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
