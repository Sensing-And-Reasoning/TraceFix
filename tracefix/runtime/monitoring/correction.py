"""Corrective-guidance formatting shared by the runtimes (Workstream B).

When a coordination call is rejected because it is out of order, the monitor
knows — from ``states.json`` — exactly which operations ARE legal now. This turns
that into a tool-result the agent can act on: a diagnosis, the legal next
actions, an optional situational hint, and the running correction-attempt count.

Both ``sdk_adapter/dispatch.py`` and ``monitoring/agent_runner.py`` format
``StateGuidanceError`` (in-process) or the equivalent RPC error dict
(distributed) through ``corrective_result`` so the agent sees one consistent
shape.
"""

from __future__ import annotations

# Consecutive unrecovered corrections at one state before we stop the agent and
# fail the run honestly (never loop forever, never fake success).
CORRECTION_CAP = 3


def describe_hint(h: dict) -> str:
    """Render a legal-action hint as the exact coordination tool call to make."""
    op = h.get("op")
    if op == "acquire":
        return f'acquire_lock("{h.get("resource")}")'
    if op == "release":
        return f'release_lock("{h.get("resource")}")'
    if op == "send":
        label = h.get("label")
        return (f'send_message("{h.get("channel")}", "{label}")' if label
                else f'send_message("{h.get("channel")}", <label>)')
    if op == "receive":
        return f'receive_message("{h.get("channel")}")'
    if op == "done":
        return "signal_done()"
    return str(h)


def corrective_result(op_type: str, op_args: dict, legal_actions: list[dict],
                      context: str = "", attempt: int = 1) -> dict:
    """Build the corrective tool-result returned to the agent after a rejection."""
    target = op_args.get("resource") or op_args.get("channel") or ""
    legal_str = (", ".join(describe_hint(h) for h in legal_actions)
                 or "(nothing — you may already be done; call signal_done())")
    msg = (f"Out-of-order coordination: '{op_type} {target}' is not allowed at "
           f"your current protocol step. Do this instead → {legal_str}.")
    if context:
        msg += f" ({context})"
    return {
        "status": "error",
        "error": "out_of_order",
        "message": msg,
        "legal_actions": legal_actions,
        "correction_attempt": attempt,
    }
