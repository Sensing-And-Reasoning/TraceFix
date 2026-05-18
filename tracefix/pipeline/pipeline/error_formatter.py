"""TLC error formatting for LLM repair prompts (PlusCal pipeline).

Converts TLC verification failures into structured, LLM-friendly feedback.
Action names in traces correspond to PlusCal labels — the agent should use
them to locate and fix the relevant code in Protocol.tla.
"""

from __future__ import annotations

import re

from tracefix.pipeline.pipeline.tlc_runner import TLCResult
from tracefix.pipeline.pipeline.trace_parser import TraceStep

# ── Constants ──────────────────────────────────────────────────────────────────

_TRACE_READING_HINT = (
    "**How to read the trace**: Each `pc` value (e.g., `c_wait`, `a_vote`) is a "
    "PlusCal label in Protocol.tla. The action name (e.g., `c_send(\"coordinator\")`) "
    "shows which label was executed. Use these to locate the relevant code in "
    "Protocol.tla and fix it with the Edit tool."
)

# Human-readable explanations for known invariant names
_INVARIANT_MEANINGS: dict[str, str] = {
    "MutualExclusion": (
        "Two agents hold the same Lock simultaneously. "
        "Add `acquire_lock` before the critical section in the offending process, "
        "or fix the guard condition so only one agent can enter at a time."
    ),
    "NoOrphanLocks": (
        "A Lock is still held when all agents reach Done. "
        "Find the code path that exits without calling `release_lock` "
        "and add the missing release."
    ),
    "ChannelsDrained": (
        "Messages remain in a channel when all agents reach Done. "
        "Find the agent that should receive from that channel and ensure "
        "it processes all messages before terminating."
    ),
    "TypeInvariant": (
        "A variable holds an unexpected value — often a misspelled channel label "
        "or an invalid lock holder. Check that all `send()` labels match the IR "
        "channel's `labels` array exactly (case-sensitive), and that lock variables "
        "only hold agent IDs or `\"FREE\"`."
    ),
}

_SHORT_TRACE_THRESHOLD = 10   # show full trace if at or below this many steps
_LONG_TRACE_TAIL = 5          # show this many tail steps for long traces

# ── Internal helpers ───────────────────────────────────────────────────────────

def _clean_action_name(action: str) -> str:
    """Strip TLA+ line/column references from action names.

    TLC outputs e.g.: c_send("coordinator") line 63, col 17 to line 66, col 52 of module Protocol
    We want just: c_send("coordinator")
    The line numbers refer to the translated TLA+ (not the PlusCal source),
    so they would confuse the agent.
    """
    return re.sub(r"\s+line \d+.*$", "", action)


def _parse_tla_function(tla_str: str) -> dict[str, str]:
    """Best-effort parse of TLA+ function/record notation into a Python dict.

    Handles both:
      [key1 |-> "val1", key2 |-> val2]
      (key1 :> "val1" @@ key2 :> val2)
    """
    result: dict[str, str] = {}
    # For unquoted values (integers, booleans), stop at comma/bracket/whitespace
    for m in re.finditer(r'(\w+)\s*(?:\|->|:>)\s*("(?:[^"\\]|\\.)*"|[^,\]\)\s]+)', tla_str):
        key = m.group(1)
        val = m.group(2).strip('"')
        result[key] = val
    return result


def _extract_violated_invariant(raw_output: str) -> str | None:
    """Extract the violated invariant name from TLC raw output."""
    m = re.search(r"Invariant\s+(\w+)\s+is violated", raw_output)
    return m.group(1) if m else None


def _format_trace_steps(trace: list[TraceStep]) -> str:
    """Format trace steps.

    If trace is short (≤ THRESHOLD steps), show all states.
    If trace is long (> THRESHOLD steps), show the last TAIL steps and
    instruct the agent to read tlc_output.log for the complete sequence.
    """
    if not trace:
        return "No counterexample trace available."

    total = len(trace)
    if total <= _SHORT_TRACE_THRESHOLD:
        shown = trace
        header = f"Complete trace ({total} states):"
    else:
        shown = trace[-_LONG_TRACE_TAIL:]
        header = (
            f"Last {_LONG_TRACE_TAIL} states of a {total}-state trace shown below.\n"
            f"The trace is long — read `tlc_output.log` for the complete sequence "
            f"to trace the root cause back to its origin."
        )

    lines = [header, ""]
    for step in shown:
        action_clean = _clean_action_name(step.action)
        lines.append(f"State {step.state_num}: <{action_clean}>")
        for var, val in step.variables.items():
            lines.append(f"  {var} = {val}")
        lines.append("")
    return "\n".join(lines)


def _infer_deadlock_pattern(final_state: TraceStep) -> str:
    """Best-effort inference of the deadlock cause from the final state variables."""
    locks_val = final_state.variables.get("locks", "")
    channels_val = final_state.variables.get("channels", "")
    counters_val = final_state.variables.get("counters", "")

    hints: list[str] = []

    # Detect lock contention: any lock not FREE
    lock_map = _parse_tla_function(locks_val)
    held = {lock: holder for lock, holder in lock_map.items() if holder != "FREE"}
    if held:
        held_str = ", ".join(f"`{lock}` held by `{agent}`" for lock, agent in held.items())
        hints.append(
            f"**Lock contention**: {held_str}. "
            f"If the lock holder is itself blocked waiting to acquire another lock "
            f"that a different agent holds → **circular wait**. "
            f"Fix: impose a global acquisition order so all agents acquire locks in the same sequence."
        )

    # Detect empty channels that may strand a receiver
    empty_chs = re.findall(r'(\w+)\s*(?:\|->|:>)\s*<<>>', channels_val)
    if empty_chs:
        ch_str = ", ".join(f"`{ch}`" for ch in empty_chs)
        hints.append(
            f"**Empty channels**: {ch_str} contain no messages. "
            f"If any agent's `pc` shows it waiting on `receive` from one of these channels, "
            f"the sender never sent on that path → **missing send**. "
            f"Find the sender's branch that exits without sending and add the missing `send`."
        )

    # Detect exhausted counters (value = 0): agent waiting on acquire_counter will block forever
    if counters_val:
        counter_map = _parse_tla_function(counters_val)
        zero_counters = [name for name, val in counter_map.items() if val == "0"]
        if zero_counters:
            ctr_str = ", ".join(f"`{c}`" for c in zero_counters)
            hints.append(
                f"**Counter at zero**: {ctr_str} = 0. "
                f"Any agent waiting on `acquire_counter` for these counters will block forever. "
                f"Check that the counter is released (incremented) on all paths before the "
                f"blocked agent tries to acquire it."
            )

    if not hints:
        hints.append(
            "Pattern not automatically identified. "
            "Read `pc`, `locks`, `channels`, and `counters` values above: "
            "find which agents are blocked and what they are waiting for."
        )

    return "\n".join(hints)


def _format_final_violation_state(final_state: TraceStep, label: str = "Violation Point") -> str:
    """Render the final state of a safety violation with reading guide."""
    lines = [
        f"### {label} — State {final_state.state_num}",
        f"Last action executed: `{_clean_action_name(final_state.action)}`",
        "",
    ]

    for var, val in final_state.variables.items():
        lines.append(f"- **{var}** = `{val}`")
    lines.append("")

    lines += [
        "**Reading guide:**",
        "- `pc`: which PlusCal label each agent was at when the invariant was violated",
        "- `locks`: `\"FREE\"` = unowned; an agent ID = that agent holds the lock",
        "- `channels`: `<<>>` = empty; non-empty = unread messages remain",
        "- `counters`: current counter values",
    ]

    return "\n".join(lines)


def _format_final_deadlock_state(final_state: TraceStep) -> str:
    """Render the final (deadlock) state with reading guide and pattern inference."""
    lines = [
        f"### Deadlock Point — State {final_state.state_num}",
        f"Last action executed: `{_clean_action_name(final_state.action)}`",
        "",
    ]

    for var, val in final_state.variables.items():
        lines.append(f"- **{var}** = `{val}`")
    lines.append("")

    lines += [
        "**Reading guide:**",
        "- `pc`: which PlusCal label each agent is currently stuck at",
        "- `locks`: `\"FREE\"` = unowned; an agent ID = that agent holds the lock",
        "- `channels`: `<<>>` = empty (a `receive` here blocks forever); "
        "non-empty = unread messages remain",
        "",
        "**Inferred cause:**",
        "",
        _infer_deadlock_pattern(final_state),
    ]

    return "\n".join(lines)


# ── Public formatters ──────────────────────────────────────────────────────────

def format_tlc_error(
    tlc_result: TLCResult,
    trace: list[TraceStep],
) -> str:
    """Format a TLC verification failure for LLM repair agent."""
    vtype = tlc_result.violation_type or "unknown"

    if vtype == "deadlock":
        return _format_deadlock(tlc_result, trace)
    elif vtype == "safety":
        return _format_safety(tlc_result, trace)
    elif vtype == "liveness":
        return _format_liveness(tlc_result, trace)
    else:
        return _format_error(tlc_result, trace)


def _format_deadlock(tlc_result: TLCResult, trace: list[TraceStep]) -> str:
    parts = [
        "## Verification Failure: DEADLOCK",
        "",
        "The system reached a state where no agent can make progress. "
        "All agents are blocked — waiting for resources, messages, or conditions "
        "that will never be satisfied.",
        "",
        _TRACE_READING_HINT,
        "",
        "### Error Trace:",
        "",
        _format_trace_steps(trace),
    ]

    if trace:
        parts += ["", _format_final_deadlock_state(trace[-1])]

    parts += [
        "",
        "Fix the PlusCal process bodies in Protocol.tla so all agents can reach their terminal states.",
    ]
    return "\n".join(parts)


def _format_safety(tlc_result: TLCResult, trace: list[TraceStep]) -> str:
    invariant = _extract_violated_invariant(tlc_result.raw_output or "")

    if invariant:
        meaning = _INVARIANT_MEANINGS.get(
            invariant,
            "Check the Protocol.tla invariant definition for what this invariant requires.",
        )
        cause_section = "\n".join([
            f"Invariant **{invariant}** was violated.",
            "",
            meaning,
        ])
    else:
        cause_section = "\n".join([
            "An invariant was violated. Could be:",
            "- **NoOrphanLocks**: A Lock is still held when all agents are Done",
            "- **ChannelsDrained**: Messages remain in a channel when all agents are Done",
            "- **MutualExclusion**: Two agents hold the same Lock simultaneously",
            "- **TypeInvariant**: A variable has an unexpected value",
        ])

    parts = [
        "## Verification Failure: SAFETY VIOLATION",
        "",
        cause_section,
        "",
        _TRACE_READING_HINT,
        "",
        "### Error Trace (states leading to violation):",
        "",
        _format_trace_steps(trace),
    ]

    if trace:
        parts += ["", _format_final_violation_state(trace[-1], label="Violation Point")]

    parts += [
        "",
        "Fix the PlusCal process bodies in Protocol.tla so no invariant is ever violated.",
    ]
    return "\n".join(parts)


def _format_liveness(tlc_result: TLCResult, trace: list[TraceStep]) -> str:
    return "\n".join([
        "## Verification Note: LIVENESS",
        "",
        "TLC reported a liveness-related issue. This system uses safety-only verification,",
        "so this is unexpected. The trace below may help diagnose the issue.",
        "",
        _TRACE_READING_HINT,
        "",
        "### Error Trace:",
        "",
        _format_trace_steps(trace),
        "",
        "Check for deadlock or unreachable states that may have been misclassified.",
    ])


def _format_error(tlc_result: TLCResult, trace: list[TraceStep]) -> str:
    lines = [
        "## Verification Failure: TLC ERROR",
        "",
        "TLC encountered an error during model checking.",
        "",
    ]
    if tlc_result.error_trace:
        lines += ["### Error Details:", "", tlc_result.error_trace[:2000], ""]

    if tlc_result.raw_output:
        output_lines = tlc_result.raw_output.strip().splitlines()[:30]
        lines += ["### TLC Output (first 30 lines):", "", *output_lines, ""]

    lines.append("Fix the PlusCal process bodies in Protocol.tla to resolve the error.")
    return "\n".join(lines)
