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

    for line in lines:
        # Match state headers like "State 1: <Initial predicate>" or "State 2: <Action ...>"
        state_match = re.match(r"State (\d+):\s*<(.+?)>", line)
        if state_match:
            # Save previous state if exists
            if in_state and current_state_num > 0:
                steps.append(TraceStep(
                    state_num=current_state_num,
                    action=current_action,
                    variables=current_vars,
                ))
            current_state_num = int(state_match.group(1))
            current_action = state_match.group(2)
            current_vars = {}
            in_state = True
            continue

        if in_state:
            # Match variable assignments like "/\ pc = ..." or "/\ locks = ..."
            var_match = re.match(r"\s*/\\\s+(\w+)\s*=\s*(.+)", line)
            if var_match:
                var_name = var_match.group(1)
                var_value = var_match.group(2).strip()
                current_vars[var_name] = var_value
                continue

            # Continuation of a variable value (multi-line)
            if line.strip() and not line.strip().startswith("/\\") and current_vars:
                last_key = list(current_vars.keys())[-1]
                current_vars[last_key] += " " + line.strip()
                continue

            # Empty line or non-matching line may end the state
            if not line.strip() and current_vars:
                # Could be end of state block, but keep going
                pass

    # Save last state
    if in_state and current_state_num > 0:
        steps.append(TraceStep(
            state_num=current_state_num,
            action=current_action,
            variables=current_vars,
        ))

    return steps
