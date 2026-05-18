"""Per-agent prompt generation from task description + IR + PlusCal spec.

Extracts each agent's PlusCal process body from Protocol.tla and generates
a system prompt that tells the agent to follow the protocol using coordination
tools (acquire_lock, release_lock, send_message, receive_message).
"""

from __future__ import annotations

import re


def extract_pluscal_process(tla_source: str, agent_id: str) -> str:
    """Extract the PlusCal process body for a given agent from Protocol.tla.

    Matches ``fair process ({agent_id}_proc`` through the closing ``}`` of that
    process block (brace-balanced).

    Returns the full process text including the ``fair process ...`` header.
    Raises ValueError if the process is not found.
    """
    # Find the start of the process
    pattern = rf"fair\s+process\s*\(\s*{re.escape(agent_id)}_proc\b"
    match = re.search(pattern, tla_source)
    if not match:
        raise ValueError(
            f"PlusCal process for agent '{agent_id}' not found "
            f"(looked for '{agent_id}_proc')")

    start = match.start()

    # Skip past the closing ')' of the process header (e.g., "(..._proc \in {Agent})")
    # to avoid matching '{Agent}' as the body opening brace
    paren_start = tla_source.index("(", match.start())
    paren_depth = 1
    pos = paren_start + 1
    while paren_depth > 0 and pos < len(tla_source):
        if tla_source[pos] == "(":
            paren_depth += 1
        elif tla_source[pos] == ")":
            paren_depth -= 1
        pos += 1
    # pos is now just past the closing ')' of the header

    # Find the opening '{' of the process body (after optional "variables ...")
    brace_start = tla_source.index("{", pos)
    depth = 1
    pos = brace_start + 1
    while depth > 0 and pos < len(tla_source):
        if tla_source[pos] == "{":
            depth += 1
        elif tla_source[pos] == "}":
            depth -= 1
        pos += 1

    return tla_source[start:pos].strip()


def _get_agent_channels(ir: dict, agent_id: str) -> tuple[list[str], list[str]]:
    """Return (send_channels, receive_channels) for an agent."""
    send_channels = []
    receive_channels = []
    for ch in ir.get("channels", []):
        from_a = ch["from"]
        from_list = [from_a] if isinstance(from_a, str) else from_a
        to_a = ch["to"]
        to_list = [to_a] if isinstance(to_a, str) else to_a

        if agent_id in from_list:
            labels = ch.get("labels", [])
            label_str = f" (labels: {', '.join(labels)})" if labels else ""
            send_channels.append(f"{ch['id']}: → {ch['to']}{label_str}")
        if agent_id in to_list:
            labels = ch.get("labels", [])
            label_str = f" (labels: {', '.join(labels)})" if labels else ""
            receive_channels.append(f"{ch['id']}: ← {ch['from']}{label_str}")

    return send_channels, receive_channels


def _get_locks(ir: dict) -> list[str]:
    """Return lock IDs from IR resources."""
    return [r["id"] for r in ir.get("resources", []) if r["type"] == "Lock"]


def generate_agent_prompt(
    agent_id: str,
    task_desc: str,
    ir: dict,
    tla_source: str,
) -> str:
    """Generate a complete system prompt for one agent.

    Args:
        agent_id: The agent's ID (e.g. "researcherA").
        task_desc: Task description markdown text.
        ir: The IR dict (topology only: agents, channels, resources).
        tla_source: Full Protocol.tla source text.

    Returns:
        A system prompt string instructing the agent to follow its PlusCal
        protocol and use coordination tools.
    """
    process_body = extract_pluscal_process(tla_source, agent_id)
    send_channels, receive_channels = _get_agent_channels(ir, agent_id)
    locks = _get_locks(ir)

    send_list = "\n".join(f"  - {ch}" for ch in send_channels) if send_channels else "  (none)"
    recv_list = "\n".join(f"  - {ch}" for ch in receive_channels) if receive_channels else "  (none)"
    lock_list = ", ".join(locks) if locks else "(none)"

    return f'''You are agent "{agent_id}" in a multi-agent system.

## Task
{task_desc.strip()}

## Your Protocol
Follow this PlusCal protocol EXACTLY. Each label (e.g., ra_write:) is a step.
Execute them in order, calling coordination tools as specified.

```pluscal
{process_body}
```

## Coordination Tools
- acquire_lock(lock_id): Blocks until lock is free. Call before accessing shared resource.
- release_lock(lock_id): Release a lock you hold. Call after done with shared resource.
- send_message(channel_id, label): Send a labeled message on a channel. Non-blocking.
- receive_message(channel_id): Block until a message arrives. Returns the label.
- signal_done(): Call this when you reach your final step to signal completion. REQUIRED.
- poll_channels(channel_ids): Non-blocking check for messages on multiple channels. Returns first message found, or {{"status": "none"}}. Use when you have a default action if no messages are waiting.
- receive_any(channel_ids): Wait for a message on any of the given channels (30s timeout). Returns the first message that arrives. Use when waiting for any of several senders.

## Topology
Channels you can SEND on:
{send_list}

Channels you can RECEIVE on:
{recv_list}

Locks available: {lock_list}

## Rules
1. Follow your protocol steps in order.
2. acquire_lock blocks — just call it and wait.
3. receive_message blocks — just call it and wait.
4. After receiving a message, check the returned label to decide your next step.
5. Use your domain tools to do actual work between coordination steps.
6. When you reach your final step (the "skip;" step), call signal_done() IMMEDIATELY. Do NOT call any other tool after signal_done().
7. When waiting for messages from multiple channels, use receive_any — do NOT try each channel one by one with receive_message.
8. When you have an alternative action available (not just receiving), use poll_channels to check non-blocking, then take the alternative if no messages.'''
