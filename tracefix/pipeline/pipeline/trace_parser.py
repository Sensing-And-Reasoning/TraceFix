"""Parse TLC counterexample traces into structured data."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class TraceStep:
    state_num: int
    action: str
    variables: dict[str, str] = field(default_factory=dict)


def parse_trace(tlc_output: str) -> list[TraceStep]:
    """Extract counterexample trace from TLC output.

    Args:
        tlc_output: Raw TLC output string

    Returns:
        List of TraceSteps representing the counterexample
    """
    steps = []
    lines = tlc_output.split("\n")
    current_state_num = 0
    current_action = ""
    current_vars: dict[str, str] = {}
    in_state = False
    # True while inside a state's variable region. A blank line closes it, so
    # trailing lines after the trace (e.g. "N states generated, ...") are not
    # glued onto the last variable as a bogus multi-line continuation.
    value_open = False

    def _flush() -> None:
        if in_state and current_state_num > 0:
            steps.append(TraceStep(
                state_num=current_state_num,
                action=current_action,
                variables=current_vars,
            ))

    for line in lines:
        # Match state headers like "State 1: <Initial predicate>" or "State 2: <Action ...>"
        state_match = re.match(r"State (\d+):\s*<(.+?)>", line)
        if state_match:
            _flush()  # save the previous state
            current_state_num = int(state_match.group(1))
            current_action = state_match.group(2)
            current_vars = {}
            in_state = True
            value_open = True
            continue

        if in_state:
            # Match variable assignments like "/\ pc = ..." or "/\ locks = ..."
            var_match = re.match(r"\s*/\\\s+(\w+)\s*=\s*(.+)", line)
            if var_match:
                current_vars[var_match.group(1)] = var_match.group(2).strip()
                value_open = True
                continue

            # A blank line terminates the current state's variable region.
            if not line.strip():
                value_open = False
                continue

            # Continuation of a multi-line variable value — only while the region
            # is still open (i.e. before the blank line that ends the block).
            if value_open and not line.strip().startswith("/\\") and current_vars:
                last_key = list(current_vars.keys())[-1]
                current_vars[last_key] += " " + line.strip()
                continue

    _flush()  # save the last state
    return steps
