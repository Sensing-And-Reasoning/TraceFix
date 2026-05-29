"""SDK-gated integration checks (no API call).

Skipped unless ``claude-agent-sdk`` is installed. These validate the
adapter↔SDK boundary offline: symbol presence, ``ClaudeAgentOptions`` fields,
and that the coordination schemas build into a real in-process MCP server.
A live ``query()`` run additionally needs the Claude CLI + credentials and is
not exercised here.
"""

from __future__ import annotations

import inspect

import pytest

pytest.importorskip("claude_agent_sdk")

from tracefix.runtime.monitoring.coord import COORD_TOOL_SCHEMAS
from tracefix.runtime.sdk_adapter.mcp_server import (
    build_agent_mcp_server, allowed_tool_names,
)


def test_sdk_exposes_symbols_the_adapter_imports():
    import claude_agent_sdk as sdk
    for name in ["tool", "create_sdk_mcp_server", "query", "ClaudeAgentOptions",
                 "AssistantMessage", "ToolUseBlock"]:
        assert hasattr(sdk, name), f"claude-agent-sdk missing {name}"


def test_claude_agent_options_accepts_adapter_kwargs():
    from claude_agent_sdk import ClaudeAgentOptions
    try:
        fields = set(inspect.signature(ClaudeAgentOptions).parameters)
    except (TypeError, ValueError):
        fields = set(getattr(ClaudeAgentOptions, "__dataclass_fields__", {}))
    for f in ["system_prompt", "mcp_servers", "allowed_tools",
              "permission_mode", "max_turns", "model"]:
        assert f in fields, f"ClaudeAgentOptions missing field {f}"
    # Constructing with the exact kwargs the runner uses must not raise.
    ClaudeAgentOptions(
        system_prompt="x", mcp_servers={"tracefix": object()},
        allowed_tools=["mcp__tracefix__acquire_lock", "Read"],
        permission_mode="bypassPermissions", max_turns=10,
    )


def test_coordination_schemas_build_into_mcp_server():
    class DummyDispatcher:
        async def dispatch(self, name, args):
            return {"status": "ok"}

    server = build_agent_mcp_server(DummyDispatcher(), list(COORD_TOOL_SCHEMAS))
    assert server is not None
    names = allowed_tool_names(COORD_TOOL_SCHEMAS)
    assert "mcp__tracefix__acquire_lock" in names
    assert len(names) == len(COORD_TOOL_SCHEMAS)
