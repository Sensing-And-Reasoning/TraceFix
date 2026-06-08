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
    "signal_done",      # H3 termination gate — server-side tracker is authoritative
    "post_content", "get_content",  # data plane (claim-check) over the wire
    "report_progress",  # observability-plane beacon (non-enforced)
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
    """Parse request line + headers + (optional) body.

    Returns (method, path, body, token) where token is the ``X-Tracefix-Token``
    header value (or None).
    """
    request_line = await reader.readline()
    if not request_line:
        return None, None, b"", None
    parts = request_line.decode("utf-8", "replace").strip().split(" ")
    method = parts[0] if parts else "GET"
    path = parts[1] if len(parts) > 1 else "/"

    content_length = 0
    token = None
    while True:
        header = await reader.readline()
        if header in (b"\r\n", b"\n", b""):
            break
        h = header.decode("utf-8", "replace")
        hl = h.lower()
        if hl.startswith("content-length:"):
            try:
                content_length = int(h.split(":", 1)[1].strip())
            except ValueError:
                content_length = 0
        elif hl.startswith("x-tracefix-token:"):
            token = h.split(":", 1)[1].strip()

    body = await reader.readexactly(content_length) if content_length > 0 else b""
    return method, path, body, token


class CoordinationService:
    """Serves an in-process CoordinationContext to remote agent nodes over HTTP."""

    def __init__(self, coord, host: str = "127.0.0.1", port: int = 8780,
                 verbose: bool = False, tokens: dict[str, str] | None = None):
        self.coord = coord          # an unchanged CoordinationContext
        self.host = host
        self.port = port
        self.verbose = verbose
        # Optional per-agent capability tokens {agent_id: token}. When set, every
        # /rpc must carry the matching token for the agent_id it acts as — so a
        # process that can reach the loopback port (e.g. an opencode agent with
        # Bash) cannot forge coordination ops AS A DIFFERENT agent. None = open
        # (in-process / trusted-loopback callers, e.g. mixed_run).
        self.tokens = tokens
        self._server: asyncio.Server | None = None

    async def _handle(self, reader: asyncio.StreamReader,
                      writer: asyncio.StreamWriter):
        try:
            method, path, body, token = await _read_request(reader)
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
                                            await self._dispatch(body, token)))
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

    async def _dispatch(self, body: bytes, token: str | None = None) -> bytes:
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
        # Capability check (H4): when tokens are configured, the caller must present
        # the token bound to the agent_id it is acting as. Stops one agent process
        # from forging coordination ops as another over the loopback port.
        if self.tokens is not None:
            claimed = args.get("agent_id")
            if claimed is None or token != self.tokens.get(claimed):
                return json.dumps({"status": "error", "error": "unauthorized",
                                   "message": f"token does not authorize agent "
                                              f"'{claimed}'"}).encode()
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
        current_phases = {}
        state_tasks = {}
        if tracker is not None:
            for v in tracker.violations:
                violations.append({
                    "agent": getattr(v, "agent", None),
                    "state": getattr(v, "current_state", None),
                    "operation": getattr(v, "operation", None),
                    "args": getattr(v, "args", None),
                })
            current_states = dict(tracker.current_states)
            current_phases = dict(tracker.current_phases)   # business phases
            state_tasks = dict(tracker.state_tasks)         # state id -> task prose
        beacons = list(getattr(self.coord, "beacons", []))  # progress beacons
        return json.dumps({"state_violations": violations,
                           "current_states": current_states,
                           "current_phases": current_phases,
                           "state_tasks": state_tasks,
                           "beacons": beacons}).encode()

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
