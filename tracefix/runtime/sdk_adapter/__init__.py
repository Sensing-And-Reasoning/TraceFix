"""Claude Agent SDK adapter for the tracefix monitoring runtime.

This package drives tracefix-verified coordination protocols using the
**Claude Agent SDK** (``claude-agent-sdk``) as the per-agent LLM harness,
instead of the built-in ``monitoring/agent_runner.py`` loop.

Design (harness-agnostic verification layer):

    tracefix produces the verified artifacts  ──►  ir.json + states.json + prompts/
                                                          │
    this adapter wraps the SAME coordination layer        ▼
    (CoordinationContext + ProtocolMonitor + StateTracker, all UNCHANGED)
    as a per-agent in-process MCP server, and lets the
    Claude Agent SDK provide the LLM loop + real tools (Read/Write/Edit/Bash).

The split:
  * ``dispatch.py``     — pure, SDK-free tool dispatch onto CoordinationContext (testable)
  * ``mcp_server.py``   — wraps a dispatcher as a Claude-Agent-SDK in-process MCP server
  * ``sdk_runner.py``   — runs ONE agent via the SDK ``query()`` loop
  * ``orchestrator.py`` — loads a workspace, wires the shared coord layer, runs N agents concurrently
  * ``cli.py``          — ``python -m tracefix.runtime.sdk_adapter run --task ... --workspace ...``

Agents are self-driven (the SDK runs each agent's loop) and coordination is
validated by the shared ProtocolMonitor + StateTracker — the same monitoring
model reused from ``tracefix.runtime.monitoring``.
"""
