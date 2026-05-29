"""SDK-free coordination tool dispatch.

``CoordToolDispatcher`` maps a (tool_name, args) call onto the tracefix
``CoordinationContext`` for a single agent. It is the SDK-independent core of
the adapter — the Claude Agent SDK MCP layer (``mcp_server.py``) is a thin
wrapper that just forwards calls here, so this logic is unit-testable without
the SDK installed or any API access.

It mirrors the dispatch logic of
``tracefix.runtime.monitoring.agent_runner.AgentRunner._execute_tool`` but
factored out so a different harness can reuse it. The ``agent_id`` is bound at
construction time (one dispatcher per agent), so the LLM never passes its own
id — that comes from the per-agent MCP server closure.
"""

from __future__ import annotations

import time
from typing import Any

from tracefix.runtime.monitoring.monitor import ProtocolViolation
from tracefix.runtime.sdk_adapter.types import ToolCall

# The 7 coordination tool names (must match COORD_TOOL_SCHEMAS in coord.py and
# the tool names referenced by tracefix-generated runtime_b prompts).
COORD_TOOL_NAMES = frozenset({
    "acquire_lock",
    "release_lock",
    "send_message",
    "receive_message",
    "poll_channels",
    "receive_any",
    "signal_done",
})


class CoordToolDispatcher:
    """Per-agent dispatcher: forwards tool calls to a shared CoordinationContext.

    Args:
        coord: the shared ``CoordinationContext`` (one instance per run).
        agent_id: the agent this dispatcher acts for (bound at construction).
        tool_registry: optional benchmark ``ToolRegistry`` for domain tools.
        event_bus: optional ``EventBus`` for live visualization.
        verbose: print each dispatched call to stderr.
    """

    def __init__(self, coord, agent_id: str, tool_registry=None,
                 event_bus=None, verbose: bool = False):
        self.coord = coord
        self.agent_id = agent_id
        self.tools = tool_registry
        self.event_bus = event_bus
        self.verbose = verbose

        self.done: bool = False
        self.premature_done: bool = False
        self.trace: list[ToolCall] = []
        self._round: int = 0

    async def dispatch(self, name: str, args: dict[str, Any]) -> dict:
        """Execute one tool call and return its result dict.

        Records a ``ToolCall`` in ``self.trace`` and (if an event bus is set)
        emits an ``agent.tool_call`` event, matching the monitoring runtime so
        the existing visualization can consume the trace unchanged.
        """
        args = args or {}
        self._round += 1
        rnd = self._round
        start = time.time()

        result = await self._run(name, args)

        elapsed = time.time() - start
        ts = time.time()
        self.trace.append(ToolCall(
            round=rnd, tool_name=name, arguments=args,
            result=result, elapsed=elapsed, timestamp=ts,
        ))
        if self.verbose:
            import sys
            print(f"  [{self.agent_id}] R{rnd:02d} {name}({args}) -> "
                  f"{result.get('status')} [{elapsed:.2f}s]", file=sys.stderr)

        if self.event_bus is not None:
            await self.event_bus.emit("agent.tool_call", {
                "agent_id": self.agent_id,
                "round": rnd,
                "tool_name": name,
                "arguments": args,
                "result": result,
                "elapsed": elapsed,
            })

        return result

    async def _run(self, name: str, args: dict[str, Any]) -> dict:
        """Inner dispatch without trace/event bookkeeping."""
        agent_id = self.agent_id

        # --- signal_done: the tracker OBSERVES, it does not block ---
        # The state tracker only advances on coordination ops (acquire/release/
        # send/receive). Protocols whose tail transitions are domain-tool / local
        # work (e.g. test -> pass -> done) never reach a tracked terminal state,
        # so a hard gate would deadlock a fully-finished agent. We therefore
        # accept signal_done and only flag it when the tracker can't confirm a
        # terminal state (premature?), consistent with "monitor observes".
        if name == "signal_done":
            tracker = getattr(self.coord, "tracker", None)
            premature = tracker is not None and not tracker.can_terminate(agent_id)
            self.done = True
            result = {"status": "done", "agent": agent_id}
            if premature:
                self.premature_done = True
                result["warning"] = (
                    "state tracker did not confirm a terminal state; accepting "
                    "signal_done anyway (monitor observes, does not block)."
                )
            return result

        # --- coordination tools: forward to CoordinationContext (all async) ---
        if name in COORD_TOOL_NAMES:
            try:
                return await self._run_coord(name, args)
            except ProtocolViolation as e:
                return {"status": "error", "message": f"Protocol violation: {e}"}
            except KeyError as e:
                return {"status": "error",
                        "message": f"Missing required argument: {e}"}

        # --- domain tools: forward to the benchmark ToolRegistry ---
        if self.tools is not None:
            # Agents sometimes pass agent_id explicitly in the args; drop it so
            # it doesn't collide with the agent_id we bind from the server side
            # (ToolRegistry.call already receives agent_id as a keyword).
            call_args = {k: v for k, v in args.items() if k != "agent_id"}
            try:
                res = await self.tools.call(name, agent_id=agent_id, **call_args)
            except Exception as e:  # noqa: BLE001 — surface domain errors to the LLM
                return {"status": "error", "message": f"{type(e).__name__}: {e}"}
            return {
                "status": "ok" if res.success else "failed",
                "result": res.to_dict(),
            }

        return {"status": "error", "message": f"Unknown tool: {name}"}

    async def _run_coord(self, name: str, args: dict[str, Any]) -> dict:
        agent_id = self.agent_id
        coord = self.coord
        if name == "acquire_lock":
            return await coord.acquire_lock(args["lock_id"], agent_id)
        if name == "release_lock":
            return await coord.release_lock(args["lock_id"], agent_id)
        if name == "send_message":
            return await coord.send(args["channel_id"], args["label"], agent_id,
                                    body=args.get("body", ""))
        if name == "receive_message":
            return await coord.receive(args["channel_id"], agent_id)
        if name == "poll_channels":
            return await coord.poll_channels(args["channel_ids"], agent_id)
        if name == "receive_any":
            return await coord.receive_any(args["channel_ids"], agent_id)
        # Unreachable: guarded by COORD_TOOL_NAMES membership.
        raise ProtocolViolation(f"Unhandled coordination tool: {name}")
