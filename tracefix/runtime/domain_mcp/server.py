"""The ``tracefix-domain`` stdio MCP server — local typed domain tools, per agent.

Mirrors ``coord_mcp/server.py`` but instead of forwarding to a coordination
dispatcher it executes local Python implementations: it loads a workspace
``tools.json`` (schemas + ``agent_ids``), keeps only the tools owned by this
agent, and calls the matching function in ``tools_impl.py``. ``impl: external``
tools are NOT served here — the runtime connects the agent to the real external
MCP server directly (config_gen adds it from ``mcp.json``); this server is only
the local-impl half.

This is the second module (besides coord_mcp) that depends on the official
``mcp`` package; it is imported lazily so the rest of tracefix imports without it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from tracefix.runtime.domain_mcp.impl_loader import load_impls

_MCP_HINT = (
    "The official `mcp` package is required for the domain MCP server. "
    "Install it with `pip install mcp` (or `pip install -e \".[opencode]\"`)."
)


def _require_mcp():
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        import mcp.types as mcp_types
    except ImportError as e:  # pragma: no cover - exercised only without mcp
        raise ImportError(_MCP_HINT) from e
    return Server, stdio_server, mcp_types


def local_tool_schemas(tools_path: str | Path, agent_id: str) -> list[dict]:
    """The ``impl: local`` tool schemas from ``tools.json`` owned by ``agent_id``.

    Filters by ``agent_ids`` (empty/missing → available to all) and by
    ``x-impl == 'local'`` (externals are served by their own MCP server)."""
    tools = json.loads(Path(tools_path).read_text())
    out = []
    for schema in tools:
        fn = schema.get("function", schema)
        if fn.get("x-impl") != "local":
            continue
        agents = fn.get("agent_ids") or []
        if agents and agent_id not in agents:
            continue
        out.append(schema)
    return out


def _tools_from_schemas(schemas: list[dict]) -> list:
    _, _, mcp_types = _require_mcp()
    tools, seen = [], set()
    for schema in schemas:
        fn = schema.get("function", schema)
        name = fn["name"]
        if name in seen:
            continue
        seen.add(name)
        tools.append(mcp_types.Tool(
            name=name,
            description=fn.get("description", ""),
            inputSchema=fn.get("parameters") or {"type": "object", "properties": {}, "required": []},
        ))
    return tools


async def _handle_call(impls, name: str, arguments: dict | None) -> list:
    """Run one local tool; serialize the result (or a structured error) as text."""
    _, _, mcp_types = _require_mcp()
    try:
        result = impls.call(name, arguments or {})
    except NotImplementedError:
        result = {"error": "not_implemented",
                  "detail": f"tool {name!r} has a stub impl — fill it in tools_impl.py"}
    except Exception as e:  # noqa: BLE001 - surface domain errors to the agent
        result = {"error": type(e).__name__, "detail": str(e)}
    return [mcp_types.TextContent(type="text", text=json.dumps(result, default=str))]


def build_server(impls, schemas: list[dict]):
    Server, _, _ = _require_mcp()
    server = Server("tracefix-domain")
    tools = _tools_from_schemas(schemas)

    @server.list_tools()
    async def _list_tools() -> list:  # noqa: D401
        return tools

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict | None) -> list:  # noqa: D401
        return await _handle_call(impls, name, arguments)

    return server


def _parse_args(argv: list[str] | None):
    p = argparse.ArgumentParser(
        prog="tracefix-domain",
        description="tracefix local domain-tool MCP server (stdio, scoped to one agent)")
    p.add_argument("--agent-id", default=os.environ.get("TRACEFIX_AGENT_ID"),
                   help="Agent this server is scoped to (env: TRACEFIX_AGENT_ID)")
    p.add_argument("--tools", default=os.environ.get("TRACEFIX_TOOLS_JSON"),
                   help="Path to the workspace tools.json (env: TRACEFIX_TOOLS_JSON)")
    p.add_argument("--impl", default=os.environ.get("TRACEFIX_TOOLS_IMPL"),
                   help="Path to tools_impl.py (env: TRACEFIX_TOOLS_IMPL)")
    args = p.parse_args(argv)
    if not args.agent_id:
        p.error("--agent-id (or TRACEFIX_AGENT_ID) is required")
    if not args.tools:
        p.error("--tools (or TRACEFIX_TOOLS_JSON) is required")
    if not args.impl:
        p.error("--impl (or TRACEFIX_TOOLS_IMPL) is required")
    return args


def main(argv: list[str] | None = None) -> None:
    """Console-script entry point (``tracefix-domain``)."""
    args = _parse_args(argv)
    _require_mcp()
    schemas = local_tool_schemas(args.tools, args.agent_id)
    impls = load_impls(args.impl)

    import anyio

    async def _amain() -> None:
        _, stdio_server, _ = _require_mcp()
        server = build_server(impls, schemas)
        print(f"tracefix-domain: agent={args.agent_id} tools={len(schemas)}",
              file=sys.stderr, flush=True)
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream,
                             server.create_initialization_options())

    anyio.run(_amain)


if __name__ == "__main__":
    main()
