"""Tests for the standalone coordination MCP server (coord_mcp/server.py).

Covers the net-new glue: OpenAI-schema → MCP Tool conversion, the call handler
forwarding to the dispatcher, dispatcher binding, arg parsing, and a real
in-memory MCP round-trip (list_tools + call_tool through the actual MCP machinery).
The coordination core + dispatcher are tested elsewhere and reused verbatim.
"""

import json

import pytest

from tracefix.runtime.coord_mcp import server as srv
from tracefix.runtime.sdk_adapter.mcp_server import flag_only_send_schemas
from tracefix.runtime.monitoring.coord import COORD_TOOL_SCHEMAS

EXPECTED_TOOLS = {
    "acquire_lock", "release_lock", "send_message", "receive_message",
    "poll_channels", "receive_any", "signal_done",
    "report_progress",  # observability beacon — auto-propagates to the MCP layer
    "post_content", "get_content",  # data-plane content store — auto-propagates too
}


class FakeDispatcher:
    """Records dispatch calls and returns a canned dict (stands in for CoordToolDispatcher)."""

    def __init__(self, ret: dict | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.ret = ret if ret is not None else {"status": "ok"}

    async def dispatch(self, name: str, args: dict) -> dict:
        self.calls.append((name, dict(args)))
        return self.ret


def _schemas():
    return flag_only_send_schemas(list(COORD_TOOL_SCHEMAS))


# --- schema → Tool conversion -------------------------------------------------

def test_tools_from_schemas_covers_the_coord_tools():
    tools = srv._tools_from_schemas(_schemas())
    assert len(tools) == len(EXPECTED_TOOLS)
    assert {t.name for t in tools} == EXPECTED_TOOLS


def test_send_message_tool_is_flag_only():
    tools = {t.name: t for t in srv._tools_from_schemas(_schemas())}
    props = tools["send_message"].inputSchema.get("properties", {})
    assert "body" not in props                      # control plane: label only
    assert "channel_id" in props and "label" in props


def test_acquire_lock_tool_schema():
    tools = {t.name: t for t in srv._tools_from_schemas(_schemas())}
    schema = tools["acquire_lock"].inputSchema
    assert schema["required"] == ["lock_id"]


# --- call handler forwards to the dispatcher ----------------------------------

@pytest.mark.asyncio
async def test_handle_call_forwards_and_wraps_as_text():
    fake = FakeDispatcher({"status": "acquired", "lock": "DOC"})
    out = await srv._handle_call(fake, "acquire_lock", {"lock_id": "DOC"})
    assert len(out) == 1 and out[0].type == "text"
    assert json.loads(out[0].text) == {"status": "acquired", "lock": "DOC"}
    assert fake.calls == [("acquire_lock", {"lock_id": "DOC"})]


@pytest.mark.asyncio
async def test_handle_call_none_args_becomes_empty_dict():
    fake = FakeDispatcher({"status": "done", "agent": "A"})
    out = await srv._handle_call(fake, "signal_done", None)
    assert json.loads(out[0].text)["status"] == "done"
    assert fake.calls == [("signal_done", {})]


@pytest.mark.asyncio
async def test_handle_call_surfaces_out_of_order_corrective_dict():
    corrective = {"status": "error", "error": "out_of_order",
                  "legal_actions": [{"op": "acquire", "resource": "DOC"}]}
    fake = FakeDispatcher(corrective)
    out = await srv._handle_call(fake, "send_message",
                                 {"channel_id": "c", "label": "go"})
    assert json.loads(out[0].text) == corrective   # agent reads the guidance


# --- dispatcher binding + arg parsing -----------------------------------------

def test_build_dispatcher_binds_agent_and_url():
    disp = srv.build_dispatcher("RESEARCHER_FM", "http://127.0.0.1:8780")
    assert disp.agent_id == "RESEARCHER_FM"
    assert disp.coord.agent_id == "RESEARCHER_FM"   # CoordClient is the backend
    assert disp.coord.host == "127.0.0.1" and disp.coord.port == 8780


def test_parse_args_requires_agent_id(monkeypatch):
    monkeypatch.delenv("TRACEFIX_AGENT_ID", raising=False)
    with pytest.raises(SystemExit):
        srv._parse_args([])


def test_parse_args_reads_env(monkeypatch):
    monkeypatch.setenv("TRACEFIX_AGENT_ID", "CHECKER")
    monkeypatch.setenv("TRACEFIX_COORD_URL", "http://host:9999")
    args = srv._parse_args([])
    assert args.agent_id == "CHECKER" and args.coord_url == "http://host:9999"


# --- real in-memory MCP round-trip (proves the server actually serves) --------

@pytest.mark.asyncio
async def test_inmemory_mcp_roundtrip_lists_and_calls():
    try:
        from mcp.shared.memory import create_connected_server_and_client_session
    except Exception:  # pragma: no cover
        pytest.skip("mcp in-memory test helper not available")

    fake = FakeDispatcher({"status": "acquired", "lock": "DOC"})
    server = srv.build_server(fake, _schemas())
    async with create_connected_server_and_client_session(server) as client:
        listed = await client.list_tools()
        assert {t.name for t in listed.tools} == EXPECTED_TOOLS
        result = await client.call_tool("acquire_lock", {"lock_id": "DOC"})
        assert json.loads(result.content[0].text) == {"status": "acquired", "lock": "DOC"}
        assert fake.calls[-1] == ("acquire_lock", {"lock_id": "DOC"})
