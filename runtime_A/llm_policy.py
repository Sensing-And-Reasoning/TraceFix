"""LLM-driven policy for agent execution with continuous conversation loop.

Instead of making an independent LLM API call for every state transition, this
policy maintains a single continuous conversation per agent.  The engine pushes
state information via an asyncio Queue, and the LLM sees new states as
``respond_decision`` tool results — keeping full conversational context.

Coordination states (acquire/send/receive/release) are auto-advanced by the
engine without calling the LLM at all.  Only BUSINESS and DECISION states
reach this policy.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from typing import Any


# ---------------------------------------------------------------------------
# respond_decision tool schema (always appended to the tool list)
# ---------------------------------------------------------------------------

RESPOND_DECISION_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "respond_decision",
        "description": (
            "Signal your decision at a choice point. "
            "Call this exactly once after any domain work is complete."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "choice": {
                    "type": "string",
                    "description": "The decision value (must match one of the listed options).",
                },
            },
            "required": ["choice"],
        },
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_options(actions: list[dict]) -> list[str]:
    """Derive a human-readable decision value for each enabled action.

    Priority:
      1. First send label (if action has ``send``)
      2. Target state name

    When labels collide (e.g. multiple "approved" sends to different channels),
    the channel name is appended as ``label@channel`` to disambiguate.
    """
    raw: list[str] = []
    for a in actions:
        sends = a.get("send", [])
        if isinstance(sends, dict):
            sends = [sends]
        if sends and sends[0].get("label"):
            raw.append((sends[0]["label"], sends[0].get("channel", "")))
        else:
            raw.append((a.get("target", "unknown"), ""))

    # Detect duplicates and disambiguate
    from collections import Counter
    label_counts = Counter(label for label, _ in raw)
    options: list[str] = []
    for label, channel in raw:
        if label_counts[label] > 1 and channel:
            options.append(f"{label}@{channel}")
        else:
            options.append(label)
    return options


# Semantic synonym tables for outcome-based choice matching.
# When the LLM returns "pass"/"fail" style text instead of a state ID,
# these tables allow _match_choice to pick the right option without a warning.
_PASS_SYNONYMS: frozenset[str] = frozenset({
    "pass", "passed", "success", "done", "complete", "completed",
    "ok", "approve", "approved", "accept", "accepted", "yes",
})
_FAIL_SYNONYMS: frozenset[str] = frozenset({
    "fail", "failed", "failure", "retry", "reject", "rejected",
    "revise", "revision", "error", "no", "decline",
})


def _annotate_options(options: list[str]) -> str:
    """Annotate decision options with semantic hints.

    Options containing ``__done__`` are labelled with "(success/complete path)"
    so the LLM can easily map a tool result to the correct choice rather than
    guessing from opaque state IDs.
    """
    parts = []
    for opt in options:
        if "__done__" in opt:
            parts.append(f'"{opt}" (success/complete path)')
        else:
            parts.append(f'"{opt}" (retry/continue path)')
    return "[" + ", ".join(parts) + "]"


def _match_choice(
    choice: str,
    options: list[str],
    actions: list[dict],
    *,
    verbose: bool = False,
    agent_id: str = "",
) -> int:
    """Map an LLM's choice string back to an action index.

    Tries exact match first, then case-insensitive, then partial match
    (handles ``label@channel`` format where LLM may send just the channel
    or just the label).  Semantic synonym matching maps "pass"/"fail" style
    choices to terminal/retry options before falling back to 0 with a warning.
    """
    # Exact
    for i, opt in enumerate(options):
        if opt == choice:
            return i
    # Case-insensitive
    lower = choice.lower()
    for i, opt in enumerate(options):
        if opt.lower() == lower:
            return i
    # Partial: choice matches either side of label@channel
    for i, opt in enumerate(options):
        if "@" in opt:
            label_part, channel_part = opt.split("@", 1)
            if lower == label_part.lower() or lower == channel_part.lower():
                return i
    # Reverse: option matches label part of choice (if LLM adds @channel)
    if "@" in choice:
        choice_label = choice.split("@", 1)[0].lower()
        for i, opt in enumerate(options):
            if opt.lower() == choice_label:
                return i
    # Semantic synonym matching — maps "pass"/"fail" to terminal/retry option
    stripped = lower.strip('"').strip("'")
    if stripped in _PASS_SYNONYMS:
        for i, opt in enumerate(options):
            if "__done__" in opt:
                return i
    elif stripped in _FAIL_SYNONYMS:
        for i, opt in enumerate(options):
            if "__done__" not in opt:
                return i
    # Fallback — warn so silent protocol deviations are visible in logs
    prefix = f"[{agent_id}] " if agent_id else ""
    print(
        f"  [LLM] WARNING: {prefix}choice {choice!r} did not match any of "
        f"{options}; defaulting to index 0",
        flush=True,
    )
    return 0


def _format_context(context: list[dict] | None) -> str:
    """Format auto-advance context log into a human-readable string.

    Highlights received channels so the LLM knows which agent sent the
    message it is now responding to.
    """
    if not context:
        return ""
    parts = []
    for step in context:
        desc = f"{step['from']}→{step['to']}"
        details = step.get("guards", []) + step.get("effects", [])
        if details:
            desc += f" ({', '.join(details)})"
        parts.append(desc)
    summary = "Auto-advanced: " + "; ".join(parts)

    # Extract received channels for a prominent hint
    recv_channels = []
    for step in context:
        for g in step.get("guards", []):
            if g.startswith("recv("):
                recv_channels.append(g)
    if recv_channels:
        summary += f" [Received: {', '.join(recv_channels)} — respond to the SAME agent/channel]"
    return summary


# ---------------------------------------------------------------------------
# _AgentLoop — per-agent background LLM conversation
# ---------------------------------------------------------------------------

class _AgentLoop:
    """Manages a single continuous LLM conversation for one agent.

    Communication with the engine is via two queues:
      - ``_state_q``: engine → loop (state_id, options, context) or None sentinel
      - ``_decision_q``: loop → engine (idx, tool_calls)

    The LLM sees one initial user message, then each ``respond_decision`` tool
    result carries the next state information — so the LLM maintains full
    conversational context across the entire run.
    """

    def __init__(
        self,
        agent_id: str,
        system_prompt: str,
        policy: LLMPolicy,
        max_history_pairs: int = 20,
    ):
        self._agent_id = agent_id
        self._system_prompt = system_prompt
        self._policy = policy
        self._max_history_pairs = max_history_pairs
        self._state_q: asyncio.Queue = asyncio.Queue()
        self._decision_q: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._history: list[dict] = [
            {"role": "system", "content": system_prompt},
        ]

    @property
    def history(self) -> list[dict]:
        return self._history

    def start(self):
        """Start the background loop task."""
        if self._task is None:
            self._task = asyncio.create_task(self._run_loop())

    def _trim_history(self) -> None:
        """Trim conversation history to prevent context contamination.

        Keeps the system prompt plus the most recent ``_max_history_pairs``
        message groups (~3 messages each: user/assistant/tool).  Prevents
        "failure inertia" when an agent retries many times and the LLM starts
        pattern-matching on accumulated failure records rather than current results.
        """
        max_tail = self._max_history_pairs * 3
        rest = self._history[1:]
        if len(rest) > max_tail:
            self._history = self._history[:1] + rest[-max_tail:]

    async def submit_state(
        self,
        state_id: str,
        options: list[str],
        actions: list[dict],
        context: list[dict] | None,
    ) -> tuple[int, list[dict]]:
        """Engine calls this to push a new state and wait for the LLM's decision."""
        self.start()  # ensure loop is running
        await self._state_q.put((state_id, options, actions, context))
        return await self._decision_q.get()

    async def stop(self):
        """Send termination sentinel and wait for loop to finish."""
        await self._state_q.put(None)
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None

    async def cancel(self):
        """Force-cancel the background task."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _run_loop(self):
        """Background task: continuous LLM function-calling conversation."""
        schemas = self._policy._build_schemas(self._agent_id)
        history = self._history

        # Wait for first state
        first = await self._state_q.get()
        if first is None:
            return
        state_id, options, actions, context = first

        # Build initial user message
        ctx_str = _format_context(context)
        if len(options) == 1:
            user_content = (
                f'You are at state "{state_id}". '
                f"{ctx_str + ' ' if ctx_str else ''}"
                f"Perform any domain work for this step, then call "
                f'respond_decision("{options[0]}") to proceed.'
            )
        else:
            user_content = (
                f'Decision needed at state "{state_id}". '
                f"{ctx_str + ' ' if ctx_str else ''}"
                f"Options: {_annotate_options(options)}. "
                f"Do any domain work needed, then call respond_decision(choice) "
                f"with the option that matches your result."
            )
        history.append({"role": "user", "content": user_content})

        # Pending respond_decision tool_call_id — will be filled with next state
        pending_tc_id: str | None = None
        tool_call_log: list[dict] = []

        while True:
            self._trim_history()
            # Call LLM (native async — no thread needed)
            try:
                response = await asyncio.wait_for(
                    self._policy._call_openai_async(history, schemas),
                    timeout=60,
                )
            except asyncio.TimeoutError:
                if self._policy._verbose:
                    print(f"  [LLM] {self._agent_id}: API timeout")
                history.append({
                    "role": "assistant", "content": "I need more time...",
                })
                history.append({
                    "role": "user",
                    "content": "Please call respond_decision(choice) now.",
                })
                continue

            msg = response.choices[0].message

            # Append assistant message
            assistant_dict: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                assistant_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            history.append(assistant_dict)

            if not msg.tool_calls:
                # Nudge
                history.append({
                    "role": "user",
                    "content": "Please call respond_decision(choice) to signal your decision.",
                })
                continue

            # Two-pass processing: execute ALL tool calls, then handle the
            # respond_decision.  This ensures every tool_call_id in the
            # assistant message gets a corresponding tool result — even if
            # the LLM batches domain tools after respond_decision in the same
            # response (which would otherwise cause an OpenAI API error).
            pending_decision_tc_id: str | None = None
            pending_decision_idx: int = 0

            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)

                if name == "respond_decision":
                    choice = args.get("choice", "")
                    tool_call_log.append({"tool": name, "args": args})
                    pending_decision_idx = _match_choice(
                        choice, options, actions,
                        verbose=self._policy._verbose,
                        agent_id=self._agent_id,
                    )
                    pending_decision_tc_id = tc.id
                else:
                    # Domain tool — always execute, even if it follows respond_decision
                    result = await self._policy._execute_domain_tool(
                        name, self._agent_id, args
                    )
                    tool_call_log.append({"tool": name, "args": args, "result": result})
                    history.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    })

            # After all tool calls processed, handle the pending decision
            if pending_decision_tc_id is not None:
                await self._decision_q.put((pending_decision_idx, tool_call_log))
                tool_call_log = []

                # Wait for next state from engine
                next_state = await self._state_q.get()
                if next_state is None:
                    # Done — send terminal tool result
                    history.append({
                        "role": "tool",
                        "tool_call_id": pending_decision_tc_id,
                        "content": json.dumps({
                            "status": "done",
                            "message": "Protocol complete. You have terminated.",
                        }),
                    })
                    return

                state_id, options, actions, context = next_state
                ctx_str = _format_context(context)

                if len(options) == 1:
                    msg_text = (
                        f"Perform domain work at state \"{state_id}\", "
                        f"then respond_decision(\"{options[0]}\")."
                    )
                else:
                    msg_text = (
                        f"Decision needed at state \"{state_id}\". "
                        f"Options: {_annotate_options(options)}. "
                        f"Call respond_decision with the option matching your result."
                    )

                tool_result = {
                    "status": "ok",
                    "new_state": state_id,
                    "options": options,
                }
                if ctx_str:
                    tool_result["context"] = ctx_str
                tool_result["message"] = msg_text

                history.append({
                    "role": "tool",
                    "tool_call_id": pending_decision_tc_id,
                    "content": json.dumps(tool_result),
                })
                # Continue while-loop naturally (no break needed)


# ---------------------------------------------------------------------------
# LLMPolicy
# ---------------------------------------------------------------------------

class LLMPolicy:
    """Policy that uses an LLM to choose among enabled actions.

    Each agent gets a continuous conversation loop (_AgentLoop) that persists
    across the entire run.  The engine auto-advances coordination states and
    only calls this policy for BUSINESS and DECISION states.
    """

    def __init__(
        self,
        prompts: dict[str, str],
        tool_registry: Any | None = None,
        model: str = "gpt-4.1-mini",
        api_key: str = "",
        verbose: bool = False,
        max_history_pairs: int = 20,
    ):
        self._prompts = prompts
        self._tools = tool_registry
        self._model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._verbose = verbose
        self._max_history_pairs = max_history_pairs
        self._loops: dict[str, _AgentLoop] = {}
        self._async_client: Any | None = None  # lazy AsyncOpenAI

    # -- public interface (matches AgentPolicy protocol) --------------------

    async def choose_action(
        self,
        agent_id: str,
        state_id: str,
        enabled_actions: list[dict],
        *,
        context: list[dict] | None = None,
    ) -> tuple[int, list[dict]]:
        options = _extract_options(enabled_actions)
        loop = self._get_loop(agent_id)

        idx, tool_calls = await loop.submit_state(
            state_id, options, enabled_actions, context
        )

        if self._verbose:
            n_domain = sum(1 for t in tool_calls if t.get("tool") != "respond_decision")
            print(f"  [LLM] {agent_id}@{state_id}: "
                  f"options={options} → idx={idx}"
                  f"{f' ({n_domain} tool calls)' if n_domain else ''}")

        return idx, tool_calls

    async def notify_done(self, agent_id: str):
        """Engine calls this when an agent reaches a terminal state."""
        loop = self._loops.get(agent_id)
        if loop is not None:
            await loop.stop()

    async def cleanup(self):
        """Cancel all remaining agent loops (called on run exit)."""
        for loop in self._loops.values():
            await loop.cancel()
        self._loops.clear()
        if self._async_client is not None:
            await self._async_client.close()
            self._async_client = None

    # -- internals ----------------------------------------------------------

    def _get_loop(self, agent_id: str) -> _AgentLoop:
        if agent_id not in self._loops:
            system_prompt = self._prompts.get(agent_id, f"You are agent {agent_id}.")
            self._loops[agent_id] = _AgentLoop(
                agent_id, system_prompt, self,
                max_history_pairs=self._max_history_pairs,
            )
        return self._loops[agent_id]

    def _build_schemas(self, agent_id: str) -> list[dict]:
        schemas: list[dict] = []
        if self._tools is not None:
            schemas.extend(self._tools.openai_schemas(agent_id))
        schemas.append(RESPOND_DECISION_SCHEMA)
        return schemas

    def _get_async_client(self):
        """Lazily create and cache an AsyncOpenAI client."""
        if self._async_client is None:
            from openai import AsyncOpenAI
            self._async_client = AsyncOpenAI(
                api_key=self._api_key, timeout=55,
            )
        return self._async_client

    async def _call_openai_async(self, messages: list[dict], tools: list[dict]):
        """Call LLM.  Uses native async client in production.

        When ``_call_openai`` has been replaced (e.g. by a MagicMock in tests),
        we detect that via ``inspect.ismethod`` and delegate to the sync mock so
        existing tests keep working without change.
        """
        # inspect.ismethod returns True only for genuine bound methods.
        # A MagicMock or plain function replacement returns False.
        if not inspect.ismethod(self._call_openai):
            return self._call_openai(messages, tools)
        client = self._get_async_client()
        return await client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools if tools else None,
        )

    def _call_openai(self, messages: list[dict], tools: list[dict]):
        """Sync fallback — only used when mocked in tests."""
        from openai import OpenAI
        client = OpenAI(api_key=self._api_key, timeout=55)
        return client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools if tools else None,
        )

    async def _execute_domain_tool(
        self, name: str, agent_id: str, args: dict
    ) -> dict:
        if self._tools is None:
            return {"status": "error", "message": f"Unknown tool: {name}"}
        try:
            result = await self._tools.call(name, agent_id=agent_id, **args)
            return {"status": "ok", "result": result.to_dict()}
        except Exception as e:
            return {"status": "error", "message": str(e)}
