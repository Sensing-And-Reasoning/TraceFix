"""Wrap a ``CoordToolDispatcher`` as a Claude-Agent-SDK in-process MCP server.

The Claude Agent SDK exposes custom in-process tools via ``@tool`` +
``create_sdk_mcp_server``. We build the tool objects *dynamically* from the
existing OpenAI-style schemas (``COORD_TOOL_SCHEMAS`` + the benchmark
``ToolRegistry`` domain schemas) so the tool names and parameters stay
identical to what the tracefix-generated prompts already reference.

One server is built per agent; every tool handler closes over that agent's
dispatcher, so the agent's identity is bound server-side (the LLM never passes
its own id).

The SDK is imported lazily inside ``build_agent_mcp_server`` so the rest of the
adapter (and its tests) can be imported without ``claude-agent-sdk`` installed.
"""

from __future__ import annotations

import copy
import json
from typing import Any

# MCP tool names are namespaced by the SDK as ``mcp__{server}__{tool}``.
SERVER_NAME = "tracefix"


def _openai_schema_to_sdk(fn_def: dict) -> tuple[str, str, dict]:
    """Extract (name, description, json_schema) from an OpenAI function def.

    The SDK's ``@tool`` accepts a JSON-Schema dict as the input schema, which
    is exactly the shape of OpenAI's ``parameters`` object.
    """
    name = fn_def["name"]
    description = fn_def.get("description", "")
    parameters = fn_def.get("parameters") or {
        "type": "object", "properties": {}, "required": [],
    }
    return name, description, parameters


def _make_handler(dispatcher, tool_name: str):
    """Build an async SDK tool handler that forwards to the dispatcher.

    Uses a factory so ``tool_name`` is bound per-tool (not captured late in a
    loop). Returns the SDK content-block result shape; coordination/domain
    errors are surfaced to the model as ``is_error`` results so it can recover.
    """
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        result = await dispatcher.dispatch(tool_name, args or {})
        is_error = result.get("status") in ("error", "failed")
        block = {"content": [{"type": "text", "text": json.dumps(result)}]}
        if is_error:
            block["is_error"] = True
        return block

    return handler


def build_agent_mcp_server(dispatcher, schemas: list[dict],
                           server_name: str = SERVER_NAME):
    """Create an in-process SDK MCP server exposing ``schemas`` for one agent.

    Args:
        dispatcher: the agent's ``CoordToolDispatcher``.
        schemas: OpenAI-style function schemas (coordination + domain) — the
            same dicts used by the monitoring runtime.
        server_name: MCP server name; tools become ``mcp__{server_name}__{tool}``.

    Returns:
        The SDK MCP server object (pass into ``ClaudeAgentOptions.mcp_servers``).

    Raises:
        ImportError: if ``claude-agent-sdk`` is not installed.
    """
    try:
        from claude_agent_sdk import tool, create_sdk_mcp_server
    except ImportError as e:  # pragma: no cover - exercised only without the SDK
        raise ImportError(
            "claude-agent-sdk is required for the SDK adapter. Install it with "
            "`pip install claude-agent-sdk` (and ensure the Claude Code CLI is "
            "available)."
        ) from e

    sdk_tools = []
    for schema in schemas:
        fn_def = schema.get("function", schema)
        name, description, parameters = _openai_schema_to_sdk(fn_def)
        handler = _make_handler(dispatcher, name)
        sdk_tools.append(tool(name, description, parameters)(handler))

    return create_sdk_mcp_server(name=server_name, version="0.1.0", tools=sdk_tools)


def allowed_tool_names(schemas: list[dict], server_name: str = SERVER_NAME) -> list[str]:
    """Namespaced MCP tool names for ``ClaudeAgentOptions.allowed_tools``."""
    names = []
    for schema in schemas:
        fn_def = schema.get("function", schema)
        names.append(f"mcp__{server_name}__{fn_def['name']}")
    return names


def flag_only_send_schemas(schemas: list[dict]) -> list[dict]:
    """Strip the free-form ``body`` field from ``send_message``.

    Coordination channels are the CONTROL PLANE: they carry only a label (a
    signal flag), exactly as the TLA+/IR model represents a message. Domain
    data/content belongs on the DATA PLANE (a shared file / artifact); the
    label signals it (Claim-Check pattern). Not exposing ``body`` to the agent
    keeps the verified protocol (flag flow) and the runtime in lockstep, and
    removes the monitoring blind spot where domain payload slipped through
    unvalidated. Returns a copy; input schemas are untouched.
    """
    out = []
    for schema in schemas:
        fn = schema.get("function", schema)
        if fn.get("name") == "send_message":
            schema = copy.deepcopy(schema)
            fn = schema.get("function", schema)
            fn.get("parameters", {}).get("properties", {}).pop("body", None)
            fn["description"] = (
                "Send a labeled signal on a channel. Non-blocking. The channel "
                "carries ONLY the label (a signal flag) — it does NOT carry data "
                "or content. To share data/feedback, write it to a file (the data "
                "plane) at an agreed path, then send the label to signal it."
            )
        out.append(schema)
    return out
