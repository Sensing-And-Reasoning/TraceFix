"""Tests for the per-agent OpenCode config generator (config_gen.py)."""

import json

from tracefix.runtime.opencode_adapter.config_gen import (
    DEFAULT_PERMISSION, agent_key, build_agent_config, to_env,
)


def test_agent_key_sanitizes():
    assert agent_key("RESEARCHER_FM") == "researcher_fm"
    assert agent_key("PLOTTER") == "plotter"
    assert agent_key("Agent-1") == "agent-1"
    assert agent_key("!!!") == "agent"


def test_mcp_server_scoped_to_agent_id():
    cfg = build_agent_config("RESEARCHER_FM", "http://127.0.0.1:8780")
    mcp = cfg["mcp"]["tracefix"]
    assert mcp["type"] == "local"
    assert mcp["command"] == [
        "tracefix-coord", "--agent-id", "RESEARCHER_FM",
        "--coord-url", "http://127.0.0.1:8780",
    ]
    assert mcp["environment"]["TRACEFIX_AGENT_ID"] == "RESEARCHER_FM"
    assert mcp["environment"]["TRACEFIX_COORD_URL"] == "http://127.0.0.1:8780"
    assert mcp["enabled"] is True


def test_timeout_budget_set_in_both_places():
    cfg = build_agent_config("A", "http://x", op_timeout_ms=120000)
    assert cfg["mcp"]["tracefix"]["timeout"] == 120000
    assert cfg["experimental"]["mcp_timeout"] == 120000


def test_agent_is_primary_task_denied_with_prompt_and_model():
    cfg = build_agent_config("RESEARCHER_FM", "http://x",
                             prompt="DO THE THING", model="anthropic/claude-sonnet-4-6")
    agent = cfg["agent"]["researcher_fm"]
    assert agent["mode"] == "primary"
    assert agent["model"] == "anthropic/claude-sonnet-4-6"
    assert agent["prompt"] == "DO THE THING"
    perm = agent["permission"]
    assert perm["*"] == "deny" and perm["task"] == "deny"
    assert perm["read"] == "allow" and perm["edit"] == "allow" and perm["bash"] == "allow"
    # the coordination MCP tools (tracefix_<tool>) must be re-allowed AFTER "*":"deny"
    assert perm["tracefix_*"] == "allow"
    keys = list(perm.keys())
    assert keys.index("*") < keys.index("tracefix_*")   # last-match-wins → allow stands


def test_no_model_omits_the_key():
    cfg = build_agent_config("A", "http://x")
    assert "model" not in cfg["agent"]["a"]


def test_custom_coord_cmd_for_venv_python():
    cfg = build_agent_config(
        "A", "http://x",
        coord_cmd=["/abs/python", "-m", "tracefix.runtime.coord_mcp"])
    cmd = cfg["mcp"]["tracefix"]["command"]
    assert cmd[:3] == ["/abs/python", "-m", "tracefix.runtime.coord_mcp"]
    assert cmd[3:] == ["--agent-id", "A", "--coord-url", "http://x"]


def test_to_env_roundtrips():
    cfg = build_agent_config("A", "http://x")
    env = to_env(cfg)
    assert json.loads(env["OPENCODE_CONFIG_CONTENT"]) == cfg


def test_default_permission_constant_not_mutated():
    cfg = build_agent_config("A", "http://x")
    cfg["agent"]["a"]["permission"]["read"] = "deny"
    assert DEFAULT_PERMISSION["read"] == "allow"


def test_token_injected_into_mcp_env_when_given():
    cfg = build_agent_config("A", "http://x", token="secret123")
    env = cfg["mcp"]["tracefix"]["environment"]
    assert env["TRACEFIX_COORD_TOKEN"] == "secret123"
    # token rides the MCP server env, never the (ps-visible) command line.
    assert "secret123" not in cfg["mcp"]["tracefix"]["command"]


def test_no_token_omits_the_env_key():
    cfg = build_agent_config("A", "http://x")
    assert "TRACEFIX_COORD_TOKEN" not in cfg["mcp"]["tracefix"]["environment"]
