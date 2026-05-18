"""Prompt generation for Baseline 2 (coordination primitives, no protocol).

Generates a system prompt that tells the agent about the task, the
available channels and resources, and how to use coordination tools.
NO PlusCal steps or operation ordering is included.
"""

from __future__ import annotations


def _get_agent_channels(ir: dict, agent_id: str) -> tuple[list[str], list[str]]:
    """Return (send_channels, receive_channels) for an agent."""
    send_channels = []
    receive_channels = []
    for ch in ir.get("channels", []):
        from_a = ch["from"]
        from_list = [from_a] if isinstance(from_a, str) else from_a
        to_a = ch["to"]
        to_list = [to_a] if isinstance(to_a, str) else to_a

        labels = ch.get("labels", [])
        label_str = f" (labels: {', '.join(labels)})" if labels else ""

        if agent_id in from_list:
            send_channels.append(f"{ch['id']}: -> {ch['to']}{label_str}")
        if agent_id in to_list:
            receive_channels.append(f"{ch['id']}: <- {ch['from']}{label_str}")

    return send_channels, receive_channels


def _get_resources(ir: dict) -> list[str]:
    """Return formatted resource descriptions."""
    resources = []
    for r in ir.get("resources", []):
        if r["type"] == "Lock":
            resources.append(f"{r['id']} (Lock — mutual exclusion)")
        elif r["type"] == "Counter":
            initial = (r.get("initial_value")
                       or r.get("initial")
                       or r.get("config", {}).get("initial", 0))
            resources.append(f"{r['id']} (Counter — {initial} slots)")
    return resources


def _get_full_topology(ir: dict) -> list[str]:
    """Return all channel from->to descriptions."""
    lines = []
    for ch in ir.get("channels", []):
        labels = ch.get("labels", [])
        label_str = f" [{', '.join(labels)}]" if labels else ""
        lines.append(f"{ch['id']}: {ch['from']} -> {ch['to']}{label_str}")
    return lines


def generate_b2_prompt(
    agent_id: str,
    task_desc: str,
    ir: dict,
) -> str:
    """Generate a system prompt for a Baseline-2 (coord primitives, no protocol) agent.

    Args:
        agent_id: The agent's ID (e.g. "builder_a").
        task_desc: Task description markdown text.
        ir: The IR dict (topology: agents, channels, resources).

    Returns:
        A system prompt string.
    """
    all_agents = [a["id"] for a in ir["agents"]]
    other_agents = [a for a in all_agents if a != agent_id]
    others_str = ", ".join(other_agents) if other_agents else "(none)"

    send_channels, recv_channels = _get_agent_channels(ir, agent_id)
    resources = _get_resources(ir)
    topology = _get_full_topology(ir)

    send_list = "\n".join(f"  - {ch}" for ch in send_channels) if send_channels else "  (none)"
    recv_list = "\n".join(f"  - {ch}" for ch in recv_channels) if recv_channels else "  (none)"
    resource_list = "\n".join(f"  - {r}" for r in resources) if resources else "  (none)"
    topology_list = "\n".join(f"  - {t}" for t in topology) if topology else "  (none)"

    return f'''You are agent "{agent_id}" in a multi-agent system.

## Task
{task_desc.strip()}

## Other Agents
{others_str}

## Your Channels
Channels you can SEND on:
{send_list}

Channels you can RECEIVE on:
{recv_list}

## Resources
{resource_list}

## Full Channel Topology (reference)
{topology_list}

## Coordination Tools
- **acquire_lock(lock_id)**: Acquire a resource. Waits up to 30s.
- **release_lock(lock_id)**: Release a resource you hold.
- **send_message(channel_id, label, body?)**: Send a labeled message on a channel. Non-blocking.
- **receive_message(channel_id)**: Wait for a message on a channel (up to 30s).
- **poll_channels(channel_ids)**: Non-blocking check for pending messages on multiple channels.
- **receive_any(channel_ids)**: Wait for a message on any of several channels (up to 30s).
- **signal_done()**: Call this when you have completed ALL your work. REQUIRED.

## Guidelines
1. Coordinate with other agents using messages and locks.
2. Acquire locks before accessing shared resources; release them when done.
3. Use messages to signal progress, request work, and share results.
4. Use your domain tools to perform actual work.
5. When ALL your work is complete, call signal_done().
'''
