"""Generate the per-agent OpenCode config (passed via ``OPENCODE_CONFIG_CONTENT``).

Each tracefix agent gets its OWN OpenCode process with its OWN config, because
OpenCode loads MCP servers once per process (no per-session scoping). The config:

- registers a stdio MCP server ``tracefix`` scoped to this agent's id (``--agent-id``)
  pointing at the central CoordinationService (``--coord-url``);
- sets both ``mcp.tracefix.timeout`` and ``experimental.mcp_timeout`` high enough
  (default 120s) that a blocking ``acquire``/``receive`` (which emits no MCP
  progress, so OpenCode's reset-on-progress is moot) never trips a spurious MCP
  timeout — the budget is ``T_coord_op(30) < T_socket(45) < T_mcp(120)``;
- defines a PRIMARY custom agent carrying the tracefix runtime prompt, with the
  ``task`` (subagent) tool denied and tools restricted to read/edit/bash so each
  agent is a single peer (its cross-agent interaction goes only through the
  coordination MCP tools, which are NOT gated by these built-in permission keys).

Schema verified against opencode `config/mcp.ts`, `config/agent.ts`,
`config/permission.ts`. Pure functions — no I/O.
"""

from __future__ import annotations

import json
import re

#: Built-in tool permissions for a tracefix peer agent: deny everything, then allow
#: the data-plane file/shell tools AND the coordination MCP tools. ``task`` (subagent
#: fan-out) is denied — a tracefix agent is one peer and keeps coordination in its
#: own session.
#:
#: IMPORTANT: opencode DOES gate MCP tools by this permission map (verified in
#: session/tools.ts), keyed ``<mcpServer>_<tool>`` — i.e. ``tracefix_acquire_lock``,
#: ``tracefix_signal_done``, etc. (mcp/index.ts: ``sanitize(server)+"_"+sanitize(tool)``).
#: Permission uses last-matching-rule-wins with glob patterns (util/wildcard.ts), so the
#: ``tracefix_*`` allow (placed AFTER ``*: deny``) re-enables all coordination tools while
#: ``*: deny`` keeps everything else off. Keep this ``tracefix`` prefix in sync with the
#: mcp server key below.
#:
#: ``doom_loop: allow`` disables opencode's built-in repeat-call detector
#: (session/processor.ts: DOOM_LOOP_THRESHOLD=3 — three identical tool+input calls in
#: a row trigger a ``doom_loop`` permission whose default ``ask`` ABORTS the turn in
#: headless ``run`` mode). Tracefix FAN-IN channels are exactly this pattern: an agent
#: drains N messages from one channel with N identical ``receive(channel)`` calls (e.g.
#: a plotter receiving "ready" from 3 researchers on one channel). Tracefix owns loop
#: control itself (CORRECTION_CAP + the 30s op timeout + the per-agent wall-clock), so
#: opencode's detector is redundant and actively breaks legitimate fan-in. Without this,
#: any agent that receives ≥3 times on one channel is killed mid-protocol.
DEFAULT_PERMISSION = {
    "*": "deny",
    "read": "allow",
    "edit": "allow",        # opencode collapses write→edit, so this enables file writes
    "bash": "allow",
    "tracefix_*": "allow",  # the coordination MCP tools (tracefix_acquire_lock, ...)
    "doom_loop": "allow",   # don't let opencode's repeat-detector kill fan-in receives
    "task": "deny",
    "webfetch": "deny",
    "websearch": "deny",
    "question": "deny",
}

DEFAULT_OP_TIMEOUT_MS = 120_000

#: Permissions for the protocol DESIGNER agent (``tracefix design``): a single
#: agent following the /tla-verify-pluscal skill headlessly. It needs file tools
#: (ir.json, Protocol.tla, prompts) and bash (the tla-verify-pluscal CLI); it has
#: no coordination MCP server and must not fan out subagents or hit the web.
#: ``doom_loop: allow`` for the same reason as the runtime: a verify→fix→verify
#: repair loop legitimately repeats near-identical bash calls.
DESIGN_PERMISSION = {
    "*": "deny",
    "read": "allow",
    "edit": "allow",        # opencode collapses write→edit, so this enables file writes
    "bash": "allow",
    "grep": "allow",
    "glob": "allow",
    "list": "allow",
    "doom_loop": "allow",
    "task": "deny",
    "webfetch": "deny",
    "websearch": "deny",
    "question": "deny",     # headless: never block on interactive questions
}


def build_design_config(prompt: str, *, model: str | None = None) -> dict:
    """OpenCode config for the single protocol-designer agent (no MCP servers).

    The design workflow's knowledge arrives as the agent ``prompt`` (the
    /tla-verify-pluscal SKILL.md + a headless preamble); its actions are plain
    file edits + the ``tla-verify-pluscal`` CLI over bash.
    """
    agent_def: dict = {
        "mode": "primary",
        "prompt": prompt,
        "permission": dict(DESIGN_PERMISSION),
    }
    if model:
        agent_def["model"] = model
    return {
        "$schema": "https://opencode.ai/config.json",
        "agent": {"designer": agent_def},
    }


def agent_key(agent_id: str) -> str:
    """A valid lowercase OpenCode agent key derived from a tracefix agent id.

    e.g. ``RESEARCHER_FM`` -> ``researcher_fm``. Deterministic, so the orchestrator
    and the driver derive the same ``--agent <key>``.
    """
    key = re.sub(r"[^a-z0-9_-]", "_", agent_id.lower()).strip("_")
    return key or "agent"


def _sanitize_server_key(name: str) -> str:
    """Lowercase alphanumeric MCP-server key so the `<key>_*` permission glob
    matches opencode's `sanitize(server)_sanitize(tool)` gating deterministically."""
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    return key or "ext"


def domain_wiring(workspace, agent_id: str, *, domain_cmd: list[str] | None = None) -> dict | None:
    """Compute the per-agent typed-tool wiring for ``build_agent_config(domain=...)``.

    Reads the workspace ``tools.json`` (+ optional ``mcp.json``) and returns, for
    ``agent_id``: a ``local`` entry (the ``tracefix-domain`` server scoped to this
    agent, present iff it owns any ``impl: local`` tool) and an ``external`` map
    (the external MCP servers whose ``agent_ids`` include this agent). Returns None
    when the agent has no typed tools — the common builtins-only case. Pure-ish I/O:
    only reads the two workspace files."""
    from pathlib import Path
    ws = Path(workspace)
    tools_path = ws / "tools.json"
    if not tools_path.exists():
        return None
    tools = json.loads(tools_path.read_text())

    owns_local = any(
        (fn := s.get("function", s)).get("x-impl") == "local"
        and (not fn.get("agent_ids") or agent_id in fn["agent_ids"])
        for s in tools
    )
    local = None
    if owns_local:
        impl_path = ws / "tools_impl.py"
        base = list(domain_cmd) if domain_cmd else ["tracefix-domain"]
        local = {
            "command": base + ["--agent-id", agent_id,
                               "--tools", str(tools_path.resolve()),
                               "--impl", str(impl_path.resolve())],
            "environment": {"TRACEFIX_AGENT_ID": agent_id},
        }

    external: dict = {}
    mcp_path = ws / "mcp.json"
    if mcp_path.exists():
        servers = json.loads(mcp_path.read_text()).get("mcpServers", {})
        for name, server in servers.items():
            agents = server.get("agent_ids") or []
            if agents and agent_id not in agents:
                continue
            # Strip our metadata keys; pass the rest through as the opencode mcp entry.
            entry = {k: v for k, v in server.items() if k not in ("agent_ids", "tools")}
            entry.setdefault("type", "local")
            external[name] = entry

    if not local and not external:
        return None
    return {"local": local, "external": external}


def build_agent_config(
    agent_id: str,
    coord_url: str,
    *,
    prompt: str = "",
    model: str | None = None,
    op_timeout_ms: int = DEFAULT_OP_TIMEOUT_MS,
    coord_cmd: list[str] | None = None,
    permission: dict | None = None,
    token: str | None = None,
    domain: dict | None = None,
) -> dict:
    """Build the OpenCode config dict for one tracefix agent.

    Args:
        agent_id: tracefix agent id (the MCP server is scoped to it).
        coord_url: URL of the central CoordinationService.
        prompt: the agent's tracefix runtime prompt (becomes the OpenCode agent ``prompt``).
        model: optional ``provider/modelID`` (else OpenCode's default).
        op_timeout_ms: MCP timeout (per-server + experimental) in ms.
        coord_cmd: base command to launch the stdio MCP server (default
            ``["tracefix-coord"]``; the orchestrator passes an absolute/`python -m`
            form so it resolves regardless of the OpenCode process PATH).
        permission: override the built-in tool permission map.
    """
    base = list(coord_cmd) if coord_cmd else ["tracefix-coord"]
    command = base + ["--agent-id", agent_id, "--coord-url", coord_url]
    key = agent_key(agent_id)
    # Per-agent capability token (env, not argv, so it isn't in the process table).
    mcp_env = {"TRACEFIX_AGENT_ID": agent_id, "TRACEFIX_COORD_URL": coord_url}
    if token:
        mcp_env["TRACEFIX_COORD_TOKEN"] = token

    agent_def: dict = {
        "mode": "primary",
        "prompt": prompt,
        "permission": dict(permission if permission is not None else DEFAULT_PERMISSION),
    }
    if model:
        agent_def["model"] = model

    mcp_servers: dict = {
        "tracefix": {
            "type": "local",
            "command": command,
            "environment": mcp_env,
            "enabled": True,
            "timeout": op_timeout_ms,
        }
    }
    # Typed domain tools for THIS agent (per-agent scoped). `domain` is computed
    # by the orchestrator from the workspace tools.json/mcp.json; None → this agent
    # has only builtins + coordination (the common case). Each added server is
    # gated by a `<serverkey>_*: allow` permission, placed after `*: deny`, and is
    # already scoped to this agent's tools — so the glob cannot leak other agents'.
    if domain:
        local = domain.get("local")
        if local:
            mcp_servers["domain"] = {
                "type": "local",
                "command": local["command"],
                "environment": local.get("environment", {}),
                "enabled": True,
                "timeout": op_timeout_ms,
            }
            agent_def["permission"]["domain_*"] = "allow"
        for name, server in (domain.get("external") or {}).items():
            skey = _sanitize_server_key(name)
            mcp_servers[skey] = {**server, "enabled": server.get("enabled", True),
                                 "timeout": server.get("timeout", op_timeout_ms)}
            agent_def["permission"][f"{skey}_*"] = "allow"

    return {
        "$schema": "https://opencode.ai/config.json",
        "mcp": mcp_servers,
        "experimental": {"mcp_timeout": op_timeout_ms},
        "agent": {key: agent_def},
    }


def to_env(config: dict) -> dict:
    """Env mapping that injects ``config`` into an OpenCode process."""
    return {"OPENCODE_CONFIG_CONTENT": json.dumps(config)}
