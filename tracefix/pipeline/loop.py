"""Core agentic loop: think -> act -> observe -> repeat.

The LLM decides which tools to call, in what order, and when to stop.
Includes context management to stay within model context windows.
"""

from __future__ import annotations

import sys
import json
from typing import Callable

from tracefix.pipeline.workspace import Workspace
from tracefix.pipeline.tool_client import AgentResponse, ToolCall, ToolClient
from tracefix.pipeline.tools import TOOL_REGISTRY

# ---------------------------------------------------------------------------
# Context management constants
# ---------------------------------------------------------------------------

# Tool results longer than this are truncated when stored in message history.
# The agent can always read_file to see full content.
MAX_RESULT_CHARS = 2000

# When total message content exceeds this, compress old turns.
# ~37.5K tokens at 4 chars/token — compress early to reduce per-turn cost.
CONTEXT_SOFT_LIMIT_CHARS = 150_000

# Keep this many recent messages uncompressed (system + user + recent turns).
KEEP_RECENT_MESSAGES = 6

# Tools that are safe to run in parallel (no workspace mutations).
READ_ONLY_TOOLS = frozenset({"read_file", "list_files", "think", "load_benchmark"})


class AgentLoop:
    """Autonomous verification agent loop.

    The LLM receives a system prompt + user message, then iteratively
    calls tools until it decides it's done (no more tool calls).

    Context management:
      1. Long tool results are truncated when stored (agent can read_file).
      2. When context approaches the soft limit, old tool results are
         compressed to short summaries while preserving message structure.
    """

    def __init__(
        self,
        tool_client: ToolClient,
        workspace: Workspace,
        system_prompt: str,
        max_turns: int = 40,
        max_consecutive_same_tool: int = 0,
        verbose: bool = False,
        max_result_chars: int = MAX_RESULT_CHARS,
        context_limit_chars: int = CONTEXT_SOFT_LIMIT_CHARS,
        summarizer_config: "LLMConfig | None" = None,
        on_turn_end: "Callable[[AgentLoop], None] | None" = None,
    ):
        self.tool_client = tool_client
        self.workspace = workspace
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]
        self.max_turns = max_turns
        self.max_consecutive_same_tool = max_consecutive_same_tool
        self.verbose = verbose
        self.max_result_chars = max_result_chars
        self.context_limit_chars = context_limit_chars
        self.summarizer_config = summarizer_config
        self.on_turn_end = on_turn_end
        self._recent_tools: list[str] = []  # for doom loop detection

    def run(self, user_message: str) -> str:
        """Run the agentic loop until the LLM is done.

        Args:
            user_message: The initial user prompt (task description or command).

        Returns:
            The final assistant text response.
        """
        self.messages.append({"role": "user", "content": user_message})
        final_text = ""

        for turn in range(1, self.max_turns + 1):
            if self.verbose:
                print(f"\n--- Turn {turn}/{self.max_turns} ---", file=sys.stderr)

            # Compress context if approaching limit
            self._maybe_compress_context()

            response = self.tool_client.chat(self.messages)

            # Track token usage
            self.workspace.total_prompt_tokens += response.usage.get("prompt_tokens", 0)
            self.workspace.total_completion_tokens += response.usage.get("completion_tokens", 0)
            self.workspace.total_cached_tokens += response.usage.get("cached_tokens", 0)

            # Accumulate text
            if response.text:
                final_text = response.text

            # No tool calls -> agent is done
            if not response.tool_calls:
                self.messages.append({
                    "role": "assistant",
                    "content": response.text or "",
                })
                if self.verbose:
                    print(f"  Agent finished (no tool calls).", file=sys.stderr)
                break

            # Append assistant message with tool calls
            self.messages.append({
                "role": "assistant",
                "content": response.text or "",
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in response.tool_calls
                ],
            })

            # Execute tool calls (parallel for read-only, sequential for mutations)
            tool_results = self._execute_tool_calls(response.tool_calls)
            for tc, result_str in tool_results:
                self.workspace.total_tool_calls += 1
                self._recent_tools.append(tc.name)

                # Truncate long results before storing in history
                stored_result = self._truncate_result(tc.name, result_str)

                # Add tool result to messages
                self.messages.append({
                    "role": "tool_result",
                    "tool_call_id": tc.id,
                    "content": stored_result,
                })

            # Incremental save after each turn
            if self.on_turn_end:
                try:
                    self.on_turn_end(self)
                except Exception:
                    pass  # don't crash the loop on save failure
        else:
            # Reached max turns
            if self.verbose:
                print(f"\n  Max turns ({self.max_turns}) reached.", file=sys.stderr)
            if not final_text:
                final_text = f"Agent reached maximum turns ({self.max_turns}) without completing."

        return final_text

    def _execute_tool(self, tc: ToolCall) -> str:
        """Execute a tool call and return the result string."""
        func = TOOL_REGISTRY.get(tc.name)
        if func is None:
            return f"ERROR: Unknown tool '{tc.name}'. Available: {', '.join(TOOL_REGISTRY.keys())}"

        if self.verbose:
            args_preview = json.dumps(tc.arguments, ensure_ascii=False)
            if len(args_preview) > 200:
                args_preview = args_preview[:200] + "..."
            print(f"  Tool: {tc.name}({args_preview})", file=sys.stderr)

        try:
            result = func(self.workspace, **tc.arguments)
        except Exception as e:
            result = f"ERROR: {type(e).__name__}: {e}"

        if self.verbose:
            preview = result[:200] + "..." if len(result) > 200 else result
            print(f"  Result: {preview}", file=sys.stderr)

        return result

    def _execute_tool_calls(self, tool_calls: list[ToolCall]) -> list[tuple[ToolCall, str]]:
        """Execute tool calls. Read-only tools run in parallel, mutations sequential."""
        # Single tool call — common case, no overhead
        if len(tool_calls) == 1:
            tc = tool_calls[0]
            if self._is_doom_loop(tc.name):
                result = (
                    f"ERROR: '{tc.name}' has been called "
                    f"{self.max_consecutive_same_tool} times consecutively. "
                    f"Try a different approach or report the issue."
                )
                if self.verbose:
                    print(f"  DOOM LOOP: {tc.name}", file=sys.stderr)
            else:
                result = self._execute_tool(tc)
            return [(tc, result)]

        # Multiple tool calls: partition into read-only (parallel) and mutating (sequential)
        read_only = [(i, tc) for i, tc in enumerate(tool_calls) if tc.name in READ_ONLY_TOOLS]
        mutating = [(i, tc) for i, tc in enumerate(tool_calls) if tc.name not in READ_ONLY_TOOLS]

        results: dict[int, tuple[ToolCall, str]] = {}

        # Parallel read-only
        if len(read_only) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(self._execute_tool, tc): (i, tc) for i, tc in read_only}
                for f in futures:
                    i, tc = futures[f]
                    results[i] = (tc, f.result())
        else:
            for i, tc in read_only:
                results[i] = (tc, self._execute_tool(tc))

        # Sequential mutating (with doom loop detection)
        for i, tc in mutating:
            if self._is_doom_loop(tc.name):
                result = (
                    f"ERROR: '{tc.name}' has been called "
                    f"{self.max_consecutive_same_tool} times consecutively. "
                    f"Try a different approach or report the issue."
                )
                if self.verbose:
                    print(f"  DOOM LOOP: {tc.name}", file=sys.stderr)
            else:
                result = self._execute_tool(tc)
            results[i] = (tc, result)

        # Return in original order
        return [results[i] for i in sorted(results)]

    def _is_doom_loop(self, tool_name: str) -> bool:
        """Check if the same tool has been called N times consecutively."""
        n = self.max_consecutive_same_tool
        if n <= 0 or len(self._recent_tools) < n:
            return False
        return all(name == tool_name for name in self._recent_tools[-n:])

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    def _truncate_result(self, tool_name: str, result: str) -> str:
        """Truncate a tool result for storage in message history.

        Long results (full IR JSON, TLA+ specs, TLC output) are truncated
        since the agent can always use read_file to see full content.
        """
        if len(result) <= self.max_result_chars:
            return result

        # For tools whose output is saved to files, hint that read_file can help
        if tool_name in ("compile_scaffold", "verify_spec"):
            hint = "(truncated — use read_file to see full content)"
        elif tool_name == "read_file":
            hint = "(truncated — content too long for context, work with the visible portion)"
        else:
            hint = "(truncated)"

        return result[: self.max_result_chars] + f"\n\n... {hint}"

    def _estimate_context_chars(self) -> int:
        """Estimate total character count across all messages."""
        total = 0
        for msg in self.messages:
            total += len(msg.get("content", "") or "")
            # Count tool call arguments too
            for tc in msg.get("tool_calls", []):
                total += len(json.dumps(tc.get("arguments", {})))
        return total

    def _maybe_compress_context(self) -> None:
        """Compress old messages if context exceeds the soft limit.

        If a summarizer is configured, collects old messages, summarizes via
        a cheap LLM, and replaces old content with stubs + injected summary.
        Falls back to truncation-based compression on failure or if no
        summarizer is configured.
        """
        total = self._estimate_context_chars()
        if total <= self.context_limit_chars:
            return

        if self.verbose:
            print(
                f"  [Context] {total:,} chars exceeds {self.context_limit_chars:,} limit, compressing...",
                file=sys.stderr,
            )

        # Indices to protect: system (0), first user (1), last N messages
        protect_start = 2  # after system + first user
        protect_end = max(protect_start, len(self.messages) - KEEP_RECENT_MESSAGES)

        if self.summarizer_config is None:
            self._truncation_compress(protect_start, protect_end, total)
            return

        # Collect compressible content for LLM summarization
        parts: list[str] = []
        for i in range(protect_start, protect_end):
            msg = self.messages[i]
            role = msg["role"]
            content = msg.get("content", "") or ""
            if role == "tool_result" and len(content) > 100:
                parts.append(f"[Tool result]: {content[:500]}")
            elif role == "assistant":
                if content:
                    parts.append(f"[Assistant]: {content[:500]}")
                for tc in msg.get("tool_calls", []):
                    parts.append(f"[Called {tc['name']}]")

        if not parts:
            return

        # Summarize via cheap LLM
        try:
            from tracefix.pipeline.pipeline.llm_client import LLMClient
            summarizer = LLMClient(self.summarizer_config)
            resp = summarizer.chat(
                system_prompt=(
                    "Summarize this agent conversation history concisely. "
                    "Preserve: task name, current IR state (agents/resources/channels), "
                    "all TLC errors encountered, repair attempts and outcomes. "
                    "Omit: raw JSON content, file contents, tool call arguments."
                ),
                user_prompt="\n\n".join(parts),
            )
            summary_text = resp.content
            # Track summarizer token usage separately — summarizer uses a different
            # (cheaper) model, so costs must be estimated at a different rate.
            self.workspace.summarizer_prompt_tokens += resp.usage.get("prompt_tokens", 0)
            self.workspace.summarizer_completion_tokens += resp.usage.get("completion_tokens", 0)
            self.workspace.summarizer_cached_tokens += resp.usage.get("cached_tokens", 0)
        except Exception as e:
            if self.verbose:
                print(f"  [Context] Summarization failed: {e}", file=sys.stderr)
            self._truncation_compress(protect_start, protect_end, total)
            return

        # Compress old messages to stubs (preserve structure for API)
        for i in range(protect_start, protect_end):
            msg = self.messages[i]
            if msg["role"] == "tool_result":
                if len(msg.get("content", "") or "") > 100:
                    msg["content"] = "(compressed)"
            elif msg["role"] == "assistant":
                if len(msg.get("content", "") or "") > 200:
                    msg["content"] = "(compressed)"
                for tc in msg.get("tool_calls", []):
                    args = tc.get("arguments", {})
                    for key, val in args.items():
                        if isinstance(val, str) and len(val) > 200:
                            args[key] = f"({len(val)} chars, compressed)"

        # Inject summary before recent messages
        self.messages.insert(protect_end, {
            "role": "user",
            "content": f"[Context summary of earlier turns]\n{summary_text}",
        })

        if self.verbose:
            new_total = self._estimate_context_chars()
            print(
                f"  [Context] Summarized: {total:,} → {new_total:,} chars",
                file=sys.stderr,
            )

    def _truncation_compress(self, protect_start: int, protect_end: int, total: int) -> None:
        """Fallback: compress old messages via truncation.

        Replaces old tool_result content with short summaries and truncates
        long assistant text/tool arguments. Preserves message structure.
        """
        compressed = 0
        for i in range(protect_start, protect_end):
            msg = self.messages[i]

            if msg["role"] == "tool_result":
                content = msg.get("content", "") or ""
                if len(content) > 100:
                    summary = content[:80] + "\n... (compressed — use read_file for full content)"
                    msg["content"] = summary
                    compressed += 1

            elif msg["role"] == "assistant":
                # Compress long assistant text (thinking/analysis)
                content = msg.get("content", "") or ""
                if len(content) > 200:
                    msg["content"] = content[:100] + "\n... (compressed)"

                # Compress tool call arguments (especially write_file content)
                for tc in msg.get("tool_calls", []):
                    args = tc.get("arguments", {})
                    for key, val in args.items():
                        if isinstance(val, str) and len(val) > 200:
                            args[key] = val[:100] + f"\n... ({len(val)} chars, compressed)"
                            compressed += 1

        if self.verbose and compressed:
            new_total = self._estimate_context_chars()
            print(
                f"  [Context] Compressed {compressed} items: "
                f"{total:,} → {new_total:,} chars",
                file=sys.stderr,
            )
