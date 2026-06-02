"""Standalone, harness-agnostic coordination MCP server.

``tracefix-coord`` is a stdio MCP server that exposes tracefix's verified
coordination tools (acquire_lock / release_lock / send_message / receive_message
/ poll_channels / receive_any / signal_done) to ANY MCP-capable agent harness
(OpenCode, Claude Agent SDK, Cursor, ...).

Each instance is scoped to ONE agent (``--agent-id``) and forwards every call to
a central ``CoordinationService`` (``--coord-url``) via ``CoordClient``. The
monitor + correction enforcement lives server-side, so it is identical across
harnesses and cannot be bypassed by the agent. The per-agent correction /
honest-failure logic is the existing ``CoordToolDispatcher``, reused verbatim.
"""
