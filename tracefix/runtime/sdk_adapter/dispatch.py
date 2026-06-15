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

from tracefix.runtime.monitoring.monitor import ProtocolViolation, StateGuidanceError
from tracefix.runtime.monitoring.correction import (
    corrective_result, describe_hint, CORRECTION_CAP)
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
                 event_bus=None, verbose: bool = False, domain_impls=None):
        self.coord = coord
        self.agent_id = agent_id
        self.tools = tool_registry
        # Local typed-tool implementations (DomainImpls from tools_impl.py); when a
        # forwarded domain call names one, it runs here instead of the schema-only
        # ToolRegistry (which has no sim to execute against).
        self.domain_impls = domain_impls
        self.event_bus = event_bus
        self.verbose = verbose

        self.done: bool = False
        self.premature_done: bool = False
        # Set when the agent makes CORRECTION_CAP consecutive out-of-order
        # coordination attempts at one step without recovering — the run then
        # fails honestly (never loops forever, never fakes success).
        self.correction_limit_exceeded: bool = False
        self._local_corrections: int = 0  # distributed-mode streak (no local tracker)
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

        # --- signal_done: coordination termination, gated by the AUTHORITATIVE tracker.
        # (H3) A done is ALLOWED only from a state that can still reach a terminal state
        # (can_terminate follows skip chains, so a domain/business tail does NOT falsely
        # block it). This stops a content message ("we're done, signal done now") from
        # terminating an agent that still owes a coordination op (e.g. a final send) and
        # stranding peers blocked on a label that never arrives (liveness).
        # The decision lives in CoordinationContext.signal_done, so it is identical
        # in-process AND over the wire: in distributed mode CoordClient.signal_done is an
        # RPC to the server-side tracker — full FSM gate, not just a held-locks fallback.
        if name == "signal_done":
            result = await self.coord.signal_done(agent_id)
            if result.get("status") == "done":
                self.done = True
                if result.get("held_locks") or result.get("warning"):
                    self.premature_done = True
            return result

        # --- report_progress: observability-plane beacon, NOT a coordination op.
        # Routed here BEFORE the COORD_TOOL_NAMES gate so it never enters the
        # validate/correction path — it can never be out of order or a violation. ---
        if name == "report_progress":
            return await self.coord.report_progress(args.get("label", ""), agent_id)

        # --- post_content / get_content: data-plane content store, NOT coordination.
        # Routed BEFORE the COORD_TOOL_NAMES gate (like report_progress) so they never
        # enter the validate/correction path — content is data, never a coordination op.
        if name == "post_content":
            return await self.coord.post_content(
                args.get("content", ""), agent_id,
                content_type=args.get("content_type", "text"))
        if name == "get_content":
            return await self.coord.get_content(args.get("ref", ""), agent_id)

        # --- coordination tools: forward to CoordinationContext (all async) ---
        if name in COORD_TOOL_NAMES:
            try:
                result = await self._run_coord(name, args)
            except StateGuidanceError as e:  # out-of-order: guide the agent back
                return self._handle_correction(
                    e.op_type, e.op_args, e.legal_actions, e.context)
            except ProtocolViolation as e:
                return {"status": "error", "message": f"Protocol violation: {e}"}
            except KeyError as e:
                return {"status": "error",
                        "message": f"Missing required argument: {e}"}
            # Distributed mode: the service returns the out-of-order error as a
            # dict instead of raising — funnel it through the same handler.
            if isinstance(result, dict) and result.get("error") == "out_of_order":
                return self._handle_correction(
                    name, args, result.get("legal_actions", []), result.get("hint", ""))
            # Progress made — reset the distributed-mode correction streak.
            if isinstance(result, dict) and result.get("status") != "error":
                self._local_corrections = 0
            return result

        # --- domain tools: local impl first, then the benchmark ToolRegistry ---
        if self.domain_impls is not None and self.domain_impls.has(name):
            call_args = {k: v for k, v in args.items() if k != "agent_id"}
            try:
                res = self.domain_impls.call(name, call_args)
            except NotImplementedError:
                return {"status": "error",
                        "message": f"tool {name!r} has a stub impl — fill it in tools_impl.py"}
            except Exception as e:  # noqa: BLE001 — surface domain errors to the LLM
                return {"status": "error", "message": f"{type(e).__name__}: {e}"}
            return {"status": "ok", "result": res}
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

    def _handle_correction(self, op_type: str, op_args: dict,
                           legal: list[dict], context: str) -> dict:
        """Turn an out-of-order rejection into corrective guidance; trip honest
        failure once the same step is missed ``CORRECTION_CAP`` times in a row."""
        tracker = getattr(self.coord, "tracker", None)
        if tracker is not None:               # in-process: authoritative streak
            streak = tracker.correction_streak(self.agent_id)
        else:                                  # distributed: local fallback
            self._local_corrections += 1
            streak = self._local_corrections
        if streak >= CORRECTION_CAP:
            self.correction_limit_exceeded = True
            self.done = True  # end the agent; the runner maps this → "correction_failed"
            do = ", ".join(describe_hint(h) for h in legal) or "signal_done()"
            return {
                "status": "error", "error": "correction_limit",
                "message": (f"Stopped: {streak} consecutive out-of-order coordination "
                            f"attempts at the same protocol step. This run will end as a "
                            f"FAILURE. The correct next step was: {do}."),
                "legal_actions": legal,
            }
        return corrective_result(op_type, op_args, legal, context, attempt=streak)

    async def _run_coord(self, name: str, args: dict[str, Any]) -> dict:
        agent_id = self.agent_id
        coord = self.coord
        if name == "acquire_lock":
            return await coord.acquire_lock(args["lock_id"], agent_id)
        if name == "release_lock":
            return await coord.release_lock(args["lock_id"], agent_id)
        if name == "send_message":
            # Channels are flag-only: forward the opaque content `ref` (gated by the
            # label in coord.send), never a free-form body.
            result = await coord.send(args["channel_id"], args["label"], agent_id,
                                      ref=args.get("ref"))
            if args.get("body"):
                result = {**result, "note": (
                    "body ignored — channels are flag-only; post_content() to get a "
                    "ref and attach it on a content-carrying label")}
            return result
        if name == "receive_message":
            return await coord.receive(args["channel_id"], agent_id)
        if name == "poll_channels":
            return await coord.poll_channels(args["channel_ids"], agent_id)
        if name == "receive_any":
            return await coord.receive_any(args["channel_ids"], agent_id)
        # Unreachable: guarded by COORD_TOOL_NAMES membership.
        raise ProtocolViolation(f"Unhandled coordination tool: {name}")
