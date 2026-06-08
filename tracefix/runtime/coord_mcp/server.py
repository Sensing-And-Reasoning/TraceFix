"""The ``tracefix-coord`` stdio MCP server.

Wraps a ``CoordToolDispatcher`` (over a ``CoordClient`` to a central
``CoordinationService``) as a standard MCP stdio server, exposing the 7
coordination tools dynamically from ``COORD_TOOL_SCHEMAS``. This is the ONE
module that depends on the official ``mcp`` package; it is imported lazily so
the rest of tracefix (and ``opencode_adapter``) imports without ``mcp`` present.

Design mirrors ``sdk_adapter/mcp_server.py`` (the Claude-SDK variant): same tool
names/schemas, same flag-only-send control/data-plane split, same dispatcher.
Only the transport differs (generic MCP stdio vs the Claude SDK's in-process MCP).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from tracefix.runtime.coordination.client import CoordClient
from tracefix.runtime.sdk_adapter.dispatch import CoordToolDispatcher
from tracefix.runtime.sdk_adapter.mcp_server import flag_only_send_schemas
from tracefix.runtime.monitoring.coord import COORD_TOOL_SCHEMAS

_MCP_HINT = (
    "The official `mcp` package is required for the coordination MCP server. "
    "Install it with `pip install mcp` (or `pip install -e \".[opencode]\"`)."
)


def _require_mcp():
    """Lazy-import the official MCP SDK with a helpful error if it's missing."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        import mcp.types as mcp_types
    except ImportError as e:  # pragma: no cover - exercised only without mcp
        raise ImportError(_MCP_HINT) from e
    return Server, stdio_server, mcp_types


def _tools_from_schemas(schemas: list[dict]) -> list:
    """Convert OpenAI-style function schemas to MCP ``Tool`` objects (deduped by name)."""
    _, _, mcp_types = _require_mcp()
    tools = []
    seen: set[str] = set()
    for schema in schemas:
        fn = schema.get("function", schema)
        name = fn["name"]
        if name in seen:
            continue
        seen.add(name)
        tools.append(mcp_types.Tool(
            name=name,
            description=fn.get("description", ""),
            inputSchema=fn.get("parameters") or {
                "type": "object", "properties": {}, "required": [],
            },
        ))
    return tools


async def _handle_call(dispatcher, name: str, arguments: dict | None) -> list:
    """Forward one tool call to the dispatcher and wrap the result as MCP content.

    The dispatcher returns a plain dict (incl. the ``out_of_order`` corrective
    result + ``correction_limit`` honest-failure). We serialize it as text so the
    agent reads the ``status`` / ``legal_actions`` and can self-correct — exactly
    the contract used by the Claude-SDK handler (``mcp_server._make_handler``).
    """
    _, _, mcp_types = _require_mcp()
    result = await dispatcher.dispatch(name, arguments or {})
    return [mcp_types.TextContent(type="text", text=json.dumps(result))]


def build_server(dispatcher, schemas: list[dict]):
    """Build a low-level MCP ``Server`` exposing ``schemas``, each forwarding to ``dispatcher``."""
    Server, _, _ = _require_mcp()
    server = Server("tracefix-coord")
    tools = _tools_from_schemas(schemas)

    @server.list_tools()
    async def _list_tools() -> list:  # noqa: D401 - MCP handler
        return tools

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict | None) -> list:  # noqa: D401
        return await _handle_call(dispatcher, name, arguments)

    return server


def build_dispatcher(agent_id: str, coord_url: str, *, socket_timeout: float | None = None,
                     token: str | None = None):
    """Build the per-agent dispatcher over a CoordClient to the central service."""
    client = CoordClient(coord_url, agent_id, socket_timeout=socket_timeout, token=token)
    return CoordToolDispatcher(client, agent_id)


def _parse_args(argv: list[str] | None):
    p = argparse.ArgumentParser(
        prog="tracefix-coord",
        description="tracefix coordination MCP server (stdio, scoped to one agent)")
    p.add_argument("--agent-id", default=os.environ.get("TRACEFIX_AGENT_ID"),
                   help="Agent identity this server is scoped to (env: TRACEFIX_AGENT_ID)")
    p.add_argument("--coord-url",
                   default=os.environ.get("TRACEFIX_COORD_URL", "http://127.0.0.1:8780"),
                   help="URL of the central CoordinationService (env: TRACEFIX_COORD_URL)")
    p.add_argument("--socket-timeout", type=float, default=None,
                   help="Override CoordClient socket read timeout (else op_timeout + 15s)")
    p.add_argument("--token", default=os.environ.get("TRACEFIX_COORD_TOKEN"),
                   help="Per-agent capability token (env: TRACEFIX_COORD_TOKEN)")
    args = p.parse_args(argv)
    if not args.agent_id:
        p.error("--agent-id (or TRACEFIX_AGENT_ID) is required")
    return args


def main(argv: list[str] | None = None) -> None:
    """Console-script entry point (``tracefix-coord``)."""
    args = _parse_args(argv)
    # Fail fast with a clear message if mcp is absent, before opening stdio.
    _require_mcp()
    dispatcher = build_dispatcher(args.agent_id, args.coord_url,
                                  socket_timeout=args.socket_timeout, token=args.token)
    schemas = flag_only_send_schemas(list(COORD_TOOL_SCHEMAS))

    import anyio

    async def _amain() -> None:
        _, stdio_server, _ = _require_mcp()
        server = build_server(dispatcher, schemas)
        print(f"tracefix-coord: agent={args.agent_id} coord={args.coord_url} "
              f"tools={len(schemas)}", file=sys.stderr, flush=True)
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream,
                             server.create_initialization_options())

    anyio.run(_amain)


if __name__ == "__main__":
    main()
