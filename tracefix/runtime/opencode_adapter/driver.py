"""Drive ONE tracefix agent as an OpenCode subprocess and collect its outcome.

Spawns ``opencode run <kickoff> --agent <key> --format json --dir <output>`` with
``OPENCODE_CONFIG_CONTENT`` carrying the per-agent config (scoped tracefix-coord
MCP server + restricted task-denied agent + prompt + model). Streams the JSONL
event stream (schema from opencode ``cli/cmd/run.ts``: each line is
``{type, timestamp, sessionID, part}``; a ``tool_use`` event carries
``part.tool`` / ``part.state.status`` / ``part.state.output``) and reconstructs
the agent's disposition (the dispatcher lives in the separate tracefix-coord
process, so we read its results off the tool stream + the central /monitoring).

This module does NOT import ``mcp`` — only the spawned tracefix-coord child does.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Callable

from tracefix.runtime.opencode_adapter.config_gen import agent_key, to_env

#: Kickoff message; the ordered protocol lives in the agent's system prompt.
KICKOFF = ("Begin your task now. Follow your protocol steps in the exact order "
           "given in your instructions, using your coordination tools.")

#: StreamReader buffer ceiling for the opencode subprocess. asyncio defaults to
#: 64 KiB per line; a single JSONL event can blow past that (an assistant
#: message embedding full PlusCal, or a large tool result), and the default
#: makes readline() raise LimitOverrunError and crash the whole run. 64 MiB is a
#: ceiling, not an allocation — only the actual line size is held in memory.
_STREAM_LIMIT = 64 * 1024 * 1024


def _try_json(value) -> dict | None:
    if not isinstance(value, str):
        return value if isinstance(value, dict) else None
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


class AgentRunState:
    """Accumulates disposition signals from an agent's OpenCode JSONL event stream.

    Pure + synchronous so it is unit-testable without spawning OpenCode.
    """

    def __init__(self) -> None:
        self.events: int = 0
        self.tool_calls: list[dict] = []
        self.signaled_done: bool = False
        self.premature_done: bool = False
        self.correction_limit: bool = False
        self.out_of_order: int = 0

    def feed(self, ev: dict) -> None:
        self.events += 1
        if ev.get("type") != "tool_use":
            return
        part = ev.get("part") or {}
        name = part.get("tool") or ""
        st = part.get("state") or {}
        status = st.get("status")
        payload = st.get("output") if status == "completed" else st.get("error")
        result = _try_json(payload)

        tc = {"tool": name, "status": status,
              "result_status": result.get("status") if isinstance(result, dict) else None}
        self.tool_calls.append(tc)

        if not isinstance(result, dict):
            return
        err = result.get("error")
        # signal_done is namespaced by opencode as <server>_signal_done; also
        # accept any tool whose result status is "done" (the coord contract).
        if name.endswith("signal_done") or result.get("status") == "done":
            self.signaled_done = True
            if result.get("warning"):
                self.premature_done = True
        if err == "correction_limit":
            self.correction_limit = True
        if err == "out_of_order":
            self.out_of_order += 1


def classify(state: AgentRunState, returncode: int | None, timed_out: bool) -> str:
    """Map the collected signals + process exit to a final agent status."""
    if timed_out:
        return "timeout"
    if state.correction_limit:
        return "correction_failed"
    if state.signaled_done:
        return "premature_done" if state.premature_done else "completed"
    if returncode not in (0, None):
        return "error"
    return "incomplete"


async def _read_lines(stream, on_line: Callable[[str], None]) -> None:
    if stream is None:
        return
    while True:
        try:
            raw = await stream.readline()
        except (asyncio.LimitOverrunError, ValueError):
            # A single JSONL event exceeded even the raised StreamReader buffer
            # (`_STREAM_LIMIT`). Don't let one oversized line kill the whole run:
            # the separator is already buffered, so drain bytes (read() ignores
            # the limit) until we pass the newline, then carry on. That one event
            # is lost to the live feed, but the design's artifacts on disk — the
            # real source of truth — are judged afterward regardless.
            while True:
                chunk = await stream.read(_STREAM_LIMIT)
                if not chunk or b"\n" in chunk:
                    break
            if not chunk:
                break
            continue
        if not raw:
            break
        on_line(raw.decode("utf-8", "replace").rstrip("\r\n"))


async def _terminate(proc, grace: float = 3.0) -> None:
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()


async def run_opencode_agent(
    agent_id: str,
    config: dict,
    *,
    opencode_cmd: list[str],
    output_dir: str | Path,
    kickoff: str = KICKOFF,
    timeout: float = 600.0,
    on_event: Callable[[str, dict], None] | None = None,
    env_overrides: dict | None = None,
) -> dict:
    """Run one agent via OpenCode; return its disposition.

    Args:
        agent_id: tracefix agent id.
        config: the per-agent OpenCode config (from ``config_gen.build_agent_config``).
        opencode_cmd: base command for the opencode binary (e.g. ``["opencode"]``).
        output_dir: the agent's working directory (``--dir``), where files land.
        kickoff: the message that starts the run (protocol is in the system prompt).
        timeout: wall-clock cap; on expiry the process is SIGTERM'd then SIGKILL'd.
        on_event: optional ``(agent_id, event_dict)`` callback for live visualization.
    """
    key = agent_key(agent_id)
    env = {**os.environ, **to_env(config), **(env_overrides or {})}
    cmd = [*opencode_cmd, "run", kickoff, "--agent", key,
           "--format", "json", "--dir", str(output_dir)]

    proc = await asyncio.create_subprocess_exec(
        *cmd, env=env, limit=_STREAM_LIMIT,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    state = AgentRunState()
    stderr_tail: list[str] = []

    def _on_stdout(line: str) -> None:
        if not line:
            return
        try:
            ev = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return
        if not isinstance(ev, dict):
            return
        state.feed(ev)
        if on_event is not None:
            try:
                on_event(agent_id, ev)
            except Exception:
                pass

    def _on_stderr(line: str) -> None:
        if line:
            stderr_tail.append(line)
            del stderr_tail[:-40]

    async def _pump() -> None:
        await asyncio.gather(
            _read_lines(proc.stdout, _on_stdout),
            _read_lines(proc.stderr, _on_stderr),
        )
        await proc.wait()

    timed_out = False
    try:
        await asyncio.wait_for(_pump(), timeout=timeout)
    except asyncio.TimeoutError:
        timed_out = True
        await _terminate(proc)
    except asyncio.CancelledError:
        # orchestrator is shutting down — don't leave an orphan opencode process
        await _terminate(proc)
        raise

    return {
        "agent_id": agent_id,
        "status": classify(state, proc.returncode, timed_out),
        "returncode": proc.returncode,
        "signaled_done": state.signaled_done,
        "premature_done": state.premature_done,
        "correction_limit": state.correction_limit,
        "out_of_order": state.out_of_order,
        "tool_calls": state.tool_calls,
        "events": state.events,
        "stderr_tail": stderr_tail[-10:],
    }
