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


def agent_key(agent_id: str) -> str:
    """A valid lowercase OpenCode agent key derived from a tracefix agent id.

    e.g. ``RESEARCHER_FM`` -> ``researcher_fm``. Deterministic, so the orchestrator
    and the driver derive the same ``--agent <key>``.
    """
    key = re.sub(r"[^a-z0-9_-]", "_", agent_id.lower()).strip("_")
    return key or "agent"


def build_agent_config(
    agent_id: str,
    coord_url: str,
    *,
    prompt: str = "",
    model: str | None = None,
    op_timeout_ms: int = DEFAULT_OP_TIMEOUT_MS,
    coord_cmd: list[str] | None = None,
    permission: dict | None = None,
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

    agent_def: dict = {
        "mode": "primary",
        "prompt": prompt,
        "permission": dict(permission if permission is not None else DEFAULT_PERMISSION),
    }
    if model:
        agent_def["model"] = model

    return {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "tracefix": {
                "type": "local",
                "command": command,
                "environment": {
                    "TRACEFIX_AGENT_ID": agent_id,
                    "TRACEFIX_COORD_URL": coord_url,
                },
                "enabled": True,
                "timeout": op_timeout_ms,
            }
        },
        "experimental": {"mcp_timeout": op_timeout_ms},
        "agent": {key: agent_def},
    }


def to_env(config: dict) -> dict:
    """Env mapping that injects ``config`` into an OpenCode process."""
    return {"OPENCODE_CONFIG_CONTENT": json.dumps(config)}
