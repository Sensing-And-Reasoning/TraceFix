"""AgentRunner: LLM function-calling loop for one agent.

Each agent has its own conversation history and loops through:
  LLM call → tool execution → append result → repeat
until the LLM stops calling tools (indicating the agent is done).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tracefix.runtime.monitoring.coord import CoordinationContext
from tracefix.runtime.monitoring.monitor import ProtocolViolation, StateGuidanceError
from tracefix.runtime.monitoring.correction import (
    corrective_result, describe_hint, CORRECTION_CAP)

if TYPE_CHECKING:
    from tracefix.runtime.monitoring.event_bus import EventBus


@dataclass
class AgentConfig:
    agent_id: str
    system_prompt: str
    tool_schemas: list[dict]
    model: str = "gpt-5-mini"
    api_key: str = ""
    verbose: bool = False


@dataclass
class ToolCall:
    """One recorded tool call with timing."""
    round: int
    tool_name: str
    arguments: dict
    result: dict
    elapsed: float  # seconds for this tool call
    timestamp: float = 0.0  # absolute time (time.time()) when tool was executed


@dataclass
class AgentResult:
    agent_id: str
    steps: int
    status: str  # "completed" | "error"
    duration: float = 0.0
    error: str | None = None
    trace: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0   # total prompt tokens across all LLM calls
    output_tokens: int = 0  # total completion tokens across all LLM calls


class AgentRunner:
    """One agent's LLM function-calling loop."""

    def __init__(
        self,
        config: AgentConfig,
        coord: CoordinationContext,
        tool_registry=None,
        event_bus: EventBus | None = None,
    ):
        self.config = config
        self.coord = coord
        self.tools = tool_registry
        self.event_bus = event_bus
        self.messages: list[dict] = []
        self.done = False
        self.correction_limit_exceeded = False
        self._steps = 0
        self.trace: list[ToolCall] = []
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0

        # Reuse a single OpenAI client across all LLM calls
        from openai import OpenAI
        api_key = config.api_key or os.environ.get("OPENAI_API_KEY", "")
        self._llm_client = OpenAI(api_key=api_key)

    async def run(self, max_rounds: int = 50) -> AgentResult:
        """Run agent until completion. Returns AgentResult."""
        t0 = time.monotonic()
        self.messages = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": "Begin your work now. Follow your protocol."},
        ]

        try:
            _round = 0
            while not self.done:
                _round += 1
                if _round > max_rounds:
                    dur = time.monotonic() - t0
                    err = f"Max rounds ({max_rounds}) exceeded"
                    if self.event_bus:
                        await self.event_bus.emit("agent.done", {
                            "agent_id": self.config.agent_id,
                            "status": "error", "steps": self._steps,
                            "duration": dur, "error": err,
                        })
                    return AgentResult(
                        self.config.agent_id, self._steps, "error", dur,
                        err, trace=list(self.trace),
                        input_tokens=self._total_input_tokens,
                        output_tokens=self._total_output_tokens)
                if self.config.verbose:
                    print(f"  [{self.config.agent_id}] LLM call #{_round}...")
                if self.event_bus:
                    await self.event_bus.emit("agent.llm_start", {
                        "agent_id": self.config.agent_id, "round": _round,
                    })
                response = await asyncio.to_thread(self._call_llm)

                # Accumulate token usage
                if response.usage:
                    in_tok = response.usage.prompt_tokens or 0
                    out_tok = response.usage.completion_tokens or 0
                    self._total_input_tokens += in_tok
                    self._total_output_tokens += out_tok
                    if self.event_bus:
                        await self.event_bus.emit("agent.llm_end", {
                            "agent_id": self.config.agent_id,
                            "round": _round,
                            "input_tokens": in_tok,
                            "output_tokens": out_tok,
                            "total_input_tokens": self._total_input_tokens,
                            "total_output_tokens": self._total_output_tokens,
                        })

                msg = response.choices[0].message
                tool_calls = msg.tool_calls

                if self.config.verbose and msg.content:
                    text = msg.content[:200]
                    print(f"  [{self.config.agent_id}] text: {text}")

                if not tool_calls:
                    self.done = True
                    if self.config.verbose:
                        print(f"  [{self.config.agent_id}] no tool calls → done")
                    break

                # Append assistant message with tool calls
                self.messages.append(msg.to_dict())

                if self.config.verbose:
                    names = [tc.function.name for tc in tool_calls]
                    print(f"  [{self.config.agent_id}] tools: {names}")

                # Execute tool calls — concurrent for all-receive rounds,
                # sequential otherwise (preserves ordering for send/acquire).
                all_receives = all(
                    tc.function.name == "receive_message" for tc in tool_calls
                )

                if all_receives and len(tool_calls) > 1:
                    await self._execute_tools_concurrent(
                        tool_calls, _round)
                else:
                    for tc in tool_calls:
                        await self._execute_one_tool(tc, _round)

            dur = time.monotonic() - t0
            final_status = ("correction_failed"
                            if self.correction_limit_exceeded else "completed")
            ar = AgentResult(
                self.config.agent_id, self._steps, final_status, dur,
                trace=list(self.trace),
                input_tokens=self._total_input_tokens,
                output_tokens=self._total_output_tokens)
            if self.event_bus:
                await self.event_bus.emit("agent.done", {
                    "agent_id": self.config.agent_id,
                    "status": final_status, "steps": self._steps,
                    "duration": dur,
                    "input_tokens": self._total_input_tokens,
                    "output_tokens": self._total_output_tokens,
                })
            return ar

        except Exception as e:
            dur = time.monotonic() - t0
            status = "error"
            ar = AgentResult(
                self.config.agent_id, self._steps, status, dur, str(e),
                trace=list(self.trace),
                input_tokens=self._total_input_tokens,
                output_tokens=self._total_output_tokens)
            if self.event_bus:
                await self.event_bus.emit("agent.done", {
                    "agent_id": self.config.agent_id,
                    "status": status, "steps": self._steps,
                    "duration": dur, "error": str(e),
                    "input_tokens": self._total_input_tokens,
                    "output_tokens": self._total_output_tokens,
                })
            return ar

    async def _execute_one_tool(self, tc, _round: int):
        """Execute a single tool call, record trace and emit events."""
        tc_t0 = time.monotonic()
        result = await self._execute_tool(tc)
        tc_dur = time.monotonic() - tc_t0

        self.messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": result,
        })
        self._steps += 1

        args = json.loads(tc.function.arguments)
        self.trace.append(ToolCall(
            round=_round,
            tool_name=tc.function.name,
            arguments=args,
            result=json.loads(result),
            elapsed=tc_dur,
            timestamp=time.time(),
        ))

        if self.event_bus:
            await self.event_bus.emit("agent.tool_call", {
                "agent_id": self.config.agent_id,
                "round": _round,
                "tool_name": tc.function.name,
                "arguments": args,
                "result": json.loads(result),
                "elapsed": tc_dur,
            })

        if self.config.verbose:
            print(f"  [{self.config.agent_id}]   {tc.function.name}({args}) → {result[:120]} [{tc_dur:.1f}s]")

    async def _execute_tools_concurrent(self, tool_calls, _round: int):
        """Execute multiple receive_message calls concurrently."""

        async def _run_one(tc):
            t0 = time.monotonic()
            result = await self._execute_tool(tc)
            elapsed = time.monotonic() - t0
            return tc, result, elapsed

        results = await asyncio.gather(*[_run_one(tc) for tc in tool_calls])

        for tc, result, tc_elapsed in results:
            self.messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
            self._steps += 1

            args = json.loads(tc.function.arguments)
            self.trace.append(ToolCall(
                round=_round,
                tool_name=tc.function.name,
                arguments=args,
                result=json.loads(result),
                elapsed=tc_elapsed,
                timestamp=time.time(),
            ))

            if self.event_bus:
                await self.event_bus.emit("agent.tool_call", {
                    "agent_id": self.config.agent_id,
                    "round": _round,
                    "tool_name": tc.function.name,
                    "arguments": args,
                    "result": json.loads(result),
                    "elapsed": tc_elapsed,
                })

            if self.config.verbose:
                print(f"  [{self.config.agent_id}]   {tc.function.name}({args}) → {result[:120]} [{tc_elapsed:.1f}s]")

    def _call_llm(self):
        """Synchronous OpenAI API call (run in thread) with retry."""
        import time as _time
        from openai import RateLimitError, APIStatusError

        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                return self._llm_client.chat.completions.create(
                    model=self.config.model,
                    messages=self.messages,
                    tools=self.config.tool_schemas if self.config.tool_schemas else None,
                )
            except RateLimitError:
                if attempt == max_retries:
                    raise
                wait = 2 ** attempt
                if self.config.verbose:
                    print(f"  [{self.config.agent_id}] Rate limited, retry in {wait}s...")
                _time.sleep(wait)
            except APIStatusError as e:
                if e.status_code in (500, 502, 503, 504) and attempt < max_retries:
                    wait = 2 ** attempt
                    if self.config.verbose:
                        print(f"  [{self.config.agent_id}] API error {e.status_code}, retry in {wait}s...")
                    _time.sleep(wait)
                else:
                    raise

    def _handle_correction(self, op_type: str, op_args: dict,
                           legal: list[dict], context: str) -> dict:
        """Corrective guidance for an out-of-order op; honest failure after the cap."""
        agent_id = self.config.agent_id
        tracker = self.coord.tracker if self.coord else None
        streak = tracker.correction_streak(agent_id) if tracker else 1
        if streak >= CORRECTION_CAP:
            self.correction_limit_exceeded = True
            self.done = True  # end the agent; the run will report correction_failed
            do = ", ".join(describe_hint(h) for h in legal) or "signal_done()"
            return {
                "status": "error", "error": "correction_limit",
                "message": (f"Stopped: {streak} consecutive out-of-order coordination "
                            f"attempts at the same protocol step. This run will end as a "
                            f"FAILURE. The correct next step was: {do}."),
                "legal_actions": legal,
            }
        return corrective_result(op_type, op_args, legal, context, attempt=streak)

    async def _execute_tool(self, tool_call) -> str:
        """Dispatch to coordination tool or domain tool."""
        name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)
        agent_id = self.config.agent_id

        if name == "report_progress":
            r = await self.coord.report_progress(args.get("label", ""), agent_id)
        elif name == "post_content":
            r = await self.coord.post_content(
                args.get("content", ""), agent_id,
                content_type=args.get("content_type", "text"))
        elif name == "get_content":
            r = await self.coord.get_content(args.get("ref", ""), agent_id)
        elif name == "signal_done":
            # Same authoritative H3 gate as the SDK/opencode dispatchers
            # (one implementation in CoordinationContext.signal_done).
            r = await self.coord.signal_done(agent_id)
            if r.get("status") == "done":
                self.done = True
        elif name in ("acquire_lock", "release_lock", "send_message",
                       "receive_message", "poll_channels", "receive_any"):
            try:
                if name == "acquire_lock":
                    r = await self.coord.acquire_lock(args["lock_id"], agent_id)
                elif name == "release_lock":
                    r = await self.coord.release_lock(args["lock_id"], agent_id)
                elif name == "send_message":
                    # Channels are flag-only: forward the opaque content `ref` (gated
                    # by the label in coord.send), never a free-form body.
                    r = await self.coord.send(args["channel_id"], args["label"],
                                              agent_id, ref=args.get("ref"))
                elif name == "receive_message":
                    r = await self.coord.receive(args["channel_id"], agent_id)
                elif name == "poll_channels":
                    r = await self.coord.poll_channels(
                        channel_ids=args["channel_ids"], agent_id=agent_id)
                elif name == "receive_any":
                    r = await self.coord.receive_any(
                        channel_ids=args["channel_ids"], agent_id=agent_id)
            except StateGuidanceError as e:  # out-of-order: guide the agent back
                r = self._handle_correction(
                    e.op_type, e.op_args, e.legal_actions, e.context)
                if self.config.verbose:
                    print(f"  [{agent_id}] correction: {r['message']}")
            except ProtocolViolation as e:
                r = {"status": "error", "message": f"Protocol violation: {e}"}
                if self.config.verbose:
                    print(f"  [{agent_id}] ProtocolViolation: {e}")
        elif self.tools:
            result = await self.tools.call(name, agent_id=agent_id, **args)
            tool_dict = result.to_dict()
            r = {"status": "ok" if tool_dict["success"] else "failed", "result": tool_dict}
            # Emit sim state after domain tool calls
            if hasattr(self.tools, '_sim') and self.tools._sim and self.event_bus:
                sim = self.tools._sim
                sim_data = {
                    "progress": sim.progress,
                    "violations_count": len(sim.violations),
                }
                if sim.violations:
                    v = sim.violations[-1]
                    sim_data["latest_violation"] = {
                        "type": v.violation_type, "agent": v.agent,
                        "tool": v.tool, "message": v.message,
                    }
                await self.event_bus.emit("sim.update", sim_data)
        else:
            r = {"status": "error", "message": f"Unknown tool: {name}"}

        return json.dumps(r)
