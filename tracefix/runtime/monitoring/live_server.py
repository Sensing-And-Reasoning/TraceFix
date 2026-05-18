"""Lightweight asyncio HTTP server for real-time visualization.

Routes:
  GET /           → HTML page (from live_view.py)
  GET /api/ir     → IR JSON
  GET /api/events → SSE stream

Zero external dependencies — uses asyncio.start_server with raw HTTP.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tracefix.runtime.monitoring.event_bus import EventBus


def _http_response(status: int, content_type: str, body: bytes,
                   extra_headers: str = "") -> bytes:
    """Build a raw HTTP/1.1 response."""
    reason = {200: "OK", 404: "Not Found"}[status]
    headers = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Access-Control-Allow-Origin: *\r\n"
        f"{extra_headers}"
        f"\r\n"
    )
    return headers.encode() + body


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    ir_json: str,
    html_content: str,
    event_bus: EventBus,
):
    """Parse HTTP request and dispatch to the right handler."""
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not request_line:
            writer.close()
            return

        line = request_line.decode("utf-8", errors="replace").strip()
        parts = line.split(" ")
        method = parts[0] if parts else "GET"
        path = parts[1] if len(parts) > 1 else "/"

        # Consume remaining headers
        while True:
            header = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if header in (b"\r\n", b"\n", b""):
                break

        if method == "GET" and path == "/":
            body = html_content.encode("utf-8")
            writer.write(_http_response(200, "text/html; charset=utf-8", body))
            await writer.drain()

        elif method == "GET" and path == "/api/ir":
            body = ir_json.encode("utf-8")
            writer.write(_http_response(200, "application/json", body))
            await writer.drain()

        elif method == "GET" and path == "/api/events":
            # SSE stream — keep connection open
            headers = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/event-stream\r\n"
                "Cache-Control: no-cache\r\n"
                "Connection: keep-alive\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "\r\n"
            )
            writer.write(headers.encode())
            await writer.drain()

            async for sse_msg in event_bus.subscribe():
                writer.write(sse_msg.encode("utf-8"))
                try:
                    await writer.drain()
                except (ConnectionResetError, BrokenPipeError):
                    break
            return  # subscribe() ended — connection closes

        else:
            body = b"Not Found"
            writer.write(_http_response(404, "text/plain", body))
            await writer.drain()

    except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def start_live_server(
    ir: dict,
    event_bus: EventBus,
    port: int = 8765,
    title: str = "",
    model: str = "",
) -> asyncio.Server:
    """Start the HTTP/SSE server and return the asyncio.Server object."""
    from tracefix.runtime.monitoring.live_view import render_live_html

    ir_json = json.dumps(ir)
    html_content = render_live_html(ir, title=title, model=model)

    async def handler(reader, writer):
        await _handle_client(reader, writer, ir_json, html_content, event_bus)

    server = await asyncio.start_server(handler, "127.0.0.1", port)
    return server


async def stop_live_server(server: asyncio.Server):
    """Gracefully stop the server."""
    server.close()
    await server.wait_closed()
