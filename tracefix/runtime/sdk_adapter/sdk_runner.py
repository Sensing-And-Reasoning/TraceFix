"""Run a single agent through the Claude Agent SDK ``query()`` loop.

This replaces ``monitoring/agent_runner.py``'s hand-rolled OpenAI loop with the
SDK's autonomous multi-turn loop. The agent's behavior comes entirely from the
tracefix-generated system prompt; its coordination tools come from the
per-agent in-process MCP server; its real-work tools (Read/Write/Edit/Bash)
come from the SDK built-ins.

Returns the same ``AgentResult`` dataclass the monitoring runtime uses, so the
trace can flow into the existing result-saver / visualizer.
"""

from __future__ import annotations

import asyncio
import time

from tracefix.runtime.sdk_adapter.types import AgentResult

# Initial user turn that kicks off the agent (matches the monitoring runtime).
_KICKOFF = "Begin your work now. Follow your protocol steps."


async def run_sdk_agent(
    *,
    agent_id: str,
    system_prompt: str,
    dispatcher,
    mcp_server,
    allowed_tools: list[str],
    server_name: str,
    model: str | None = None,
    max_rounds: int = 50,
    verbose: bool = False,
    cwd: str | None = None,
) -> AgentResult:
    """Drive one agent to completion (or its turn cap) via the SDK.

    Args:
        agent_id: agent identity (for the result/trace).
        system_prompt: full tracefix-generated prompt (used verbatim).
        dispatcher: the agent's ``CoordToolDispatcher`` (holds the live trace).
        mcp_server: the per-agent in-process MCP server from ``build_agent_mcp_server``.
        allowed_tools: namespaced coordination/domain tool names + any built-ins.
        server_name: MCP server name used when registering ``mcp_server``.
        model: optional model override (omitted → SDK/CLI default).
        max_rounds: hard cap on agent turns (``ClaudeAgentOptions.max_turns``).
        verbose: print SDK-level tool_use blocks to stderr.

    Returns:
        ``AgentResult`` with status completed/incomplete/error and the dispatcher trace.
    """
    from claude_agent_sdk import (
        query, ClaudeAgentOptions, AssistantMessage, ToolUseBlock,
    )

    opt_kwargs: dict = dict(
        system_prompt=system_prompt,
        mcp_servers={server_name: mcp_server},
        allowed_tools=allowed_tools,
        permission_mode="bypassPermissions",
        max_turns=max_rounds,
    )
    if model:
        opt_kwargs["model"] = model
    if cwd:
        # Domain file ops (Read/Write/Edit/Bash) happen here, so runtime artifacts
        # land in the workspace instead of wherever the command was launched.
        opt_kwargs["cwd"] = cwd
    options = ClaudeAgentOptions(**opt_kwargs)

    start = time.time()
    status = "incomplete"
    error: str | None = None

    # Retry the SDK query on failure ONLY while the agent has made no progress
    # (e.g. an Anthropic/OpenAI 429/529 on the first turn — surfaced by the CLI
    # as is_error=True + subtype="success"). Retrying after progress would re-run
    # already-executed tool calls and corrupt coordination state, so we never do.
    max_query_retries = 2
    attempt = 0
    while True:
        try:
            async for message in query(prompt=_KICKOFF, options=options):
                if verbose and isinstance(message, AssistantMessage):
                    import sys
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            print(f"  [{agent_id}] sdk tool_use: {block.name}",
                                  file=sys.stderr)
                if dispatcher.done:
                    # done set either by a clean signal_done or by the correction
                    # cap (honest failure) — the latter must NOT read as completed.
                    status = ("correction_failed"
                              if dispatcher.correction_limit_exceeded else "completed")
            break  # query finished normally
        except Exception as e:  # noqa: BLE001 — record and report, don't crash the run
            if not dispatcher.trace and attempt < max_query_retries:
                attempt += 1
                if verbose:
                    import sys
                    print(f"  [{agent_id}] sdk query failed ({type(e).__name__}); "
                          f"no progress yet — retry {attempt}/{max_query_retries}",
                          file=sys.stderr)
                await asyncio.sleep(2 ** attempt)  # backoff: 2s, 4s
                continue
            error = f"{type(e).__name__}: {e}"
            status = "error"
            break

    if dispatcher.done and status != "error":
        status = ("correction_failed"
                  if dispatcher.correction_limit_exceeded else "completed")

    duration = time.time() - start
    return AgentResult(
        agent_id=agent_id,
        steps=len(dispatcher.trace),
        status=status,
        duration=duration,
        error=error,
        trace=dispatcher.trace,
    )
