"""Prompt generation for Baseline 1 (group chat).

Generates a system prompt that tells the agent about the task, its
identity, the other agents, and how to use the group chat tools.
No locks, channels, or protocol steps are included.
"""

from __future__ import annotations


def generate_b1_prompt(
    agent_id: str,
    task_desc: str,
    ir: dict,
) -> str:
    """Generate a system prompt for a Baseline-1 (group chat) agent.

    Args:
        agent_id: The agent's ID (e.g. "builder_a").
        task_desc: Task description markdown text.
        ir: The IR dict (used only for extracting agent list).

    Returns:
        A system prompt string.
    """
    all_agents = [a["id"] for a in ir["agents"]]
    other_agents = [a for a in all_agents if a != agent_id]
    others_str = ", ".join(other_agents) if other_agents else "(none)"

    return f'''You are agent "{agent_id}" in a multi-agent system.

## Task
{task_desc.strip()}

## Other Agents
{others_str}

## Communication
You are in a shared group chat with all other agents. Use these tools:

- **send_message(channel_id="group_chat", label, body)**: Send a message to the group chat. All agents can see it. Use `label` for a short tag (e.g., "update", "request") and `body` for the full message content.
- **receive_message(channel_id="group_chat")**: Read any new unread messages from the group chat. If no new messages, waits up to 15 seconds.
- **signal_done()**: Call this when you have completed ALL your work. You MUST call this — do NOT just stop.

## Resource Contention
If the task involves shared resources (e.g., shared files, databases, equipment, build slots), multiple agents may need the same resource at the same time. You have NO locks or reservations — the ONLY way to avoid conflicts is through group chat coordination:

1. **Announce before accessing**: Before you use a shared resource, send a message like "I need to use core_lib now, is anyone using it?"
2. **Wait for acknowledgment**: Do NOT proceed until other agents who might also need that resource have responded. If someone else is using it, wait and check back.
3. **Announce when done**: After you finish with a shared resource, send a message like "I'm done with core_lib, it's free now."
4. **Respect others' claims**: If another agent announced they are using a resource, do NOT use it until they say they are done.

Think of this like a shared workspace with no locks on the door — you must call out and coordinate verbally to avoid stepping on each other's work.

## Guidelines
1. **Coordinate first, act second.** When a task involves shared resources, always negotiate access in the group chat before doing work.
2. Periodically call receive_message() to check for updates from other agents. Do NOT go many rounds without reading.
3. Announce what you are doing and what you have completed, so others can plan accordingly.
4. Use your domain tools to perform actual work.
5. When ALL your work is complete, call signal_done().
'''
