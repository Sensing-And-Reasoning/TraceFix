"""OpenCode adapter — run a tracefix MAS with OpenCode as the per-agent harness.

Each tracefix agent runs as one independent top-level OpenCode process (a peer),
configured with a per-agent ``tracefix-coord`` stdio MCP server scoped to its
agent id. All agents share ONE central ``CoordinationService`` (the verified
monitor + correction enforcement). This module owns only the harness glue
(config generation + process driving + result collection); the coordination
core is reused unchanged from ``coordination/`` + ``monitoring/``.

This package imports without the optional ``mcp`` dependency — only the
spawned ``tracefix-coord`` child process needs it.
"""
