"""Chat coordination adapter for Baseline 1 (group chat).

SharedChat: broadcast message board with per-agent read cursors.
ChatCoordinationContext: duck-types tracefix.runtime.monitoring.coord.CoordinationContext so
    AgentRunner._execute_tool dispatches work here without any modification.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# SharedChat: group-chat message board
# ---------------------------------------------------------------------------

@dataclass
class ChatMessage:
    sender: str
    label: str
    body: str
    timestamp: float = field(default_factory=time.time)


class SharedChat:
    """Shared group-chat message board with per-agent read cursors.

    Uses asyncio.Condition (not Event) to avoid the signal-loss race
    condition where clear() between set() and wait() drops the wake-up.

    Self-messages are filtered out: agents never see their own messages
    in read results (they already know what they sent).  The cursor still
    advances past self-messages so they are not re-checked.
    """

    def __init__(self, agent_ids: list[str]):
        self._messages: list[ChatMessage] = []
        self._cursors: dict[str, int] = {aid: 0 for aid in agent_ids}
        self._cond = asyncio.Condition()

    def _unread_from_others(self, agent_id: str) -> list[ChatMessage]:
        """Return unread messages NOT sent by *agent_id* (no cursor change)."""
        cursor = self._cursors.get(agent_id, 0)
        return [m for m in self._messages[cursor:] if m.sender != agent_id]

    async def send(self, sender: str, label: str, body: str) -> None:
        """Append a message and wake any waiting readers."""
        msg = ChatMessage(sender=sender, label=label, body=body)
        self._messages.append(msg)
        async with self._cond:
            self._cond.notify_all()

    async def read_messages(
        self, agent_id: str, timeout: float = 15.0,
    ) -> list[ChatMessage]:
        """Return unread messages from OTHER agents.

        If no unread messages from others, waits up to *timeout* seconds.
        Returns list of ChatMessage (may be empty on timeout).
        Self-messages are skipped (cursor still advances past them).
        """
        if not self._unread_from_others(agent_id):
            # No unread messages from others — wait for new ones
            deadline = asyncio.get_event_loop().time() + timeout
            async with self._cond:
                while not self._unread_from_others(agent_id):
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        await asyncio.wait_for(
                            self._cond.wait(), timeout=remaining)
                    except asyncio.TimeoutError:
                        break

        others = self._unread_from_others(agent_id)
        self._cursors[agent_id] = len(self._messages)
        return others

    def peek(self, agent_id: str) -> list[ChatMessage]:
        """Non-blocking check for unread messages from others (no cursor advance)."""
        return self._unread_from_others(agent_id)

    def consume(self, agent_id: str) -> list[ChatMessage]:
        """Non-blocking read: return unread messages from others and advance cursor."""
        others = self._unread_from_others(agent_id)
        self._cursors[agent_id] = len(self._messages)
        return others


# ---------------------------------------------------------------------------
# Null monitor stub (for result_saver compatibility)
# ---------------------------------------------------------------------------

class _NullChatMonitor:
    """Stub that satisfies result_saver expectations (monitor.trace)."""

    @property
    def trace(self) -> list:
        return []


# ---------------------------------------------------------------------------
# ChatCoordinationContext: adapter for AgentRunner
# ---------------------------------------------------------------------------

def _format_messages(msgs: list[ChatMessage]) -> str:
    """Format chat messages as text body for LLM consumption."""
    if not msgs:
        return ""
    return "\n".join(f"[{m.sender}|{m.label}]: {m.body}" for m in msgs)


class ChatCoordinationContext:
    """Adapter: makes SharedChat duck-type compatible with CoordinationContext.

    AgentRunner._execute_tool dispatches to self.coord.send(),
    self.coord.receive(), etc. This class implements the same async
    method signatures so AgentRunner works without modification.
    """

    def __init__(self, chat: SharedChat, agent_ids: list[str], event_bus=None):
        self.chat = chat
        self.agent_ids = agent_ids
        self.event_bus = event_bus
        # Stubs for result_saver / orchestrator compatibility
        self.monitor = _NullChatMonitor()
        self.tracker = None

    async def send(
        self,
        channel_id: str,
        label: str,
        agent_id: str,
        body: str = "",
    ) -> dict:
        """Broadcast a message via group chat."""
        await self.chat.send(agent_id, label, body)
        result: dict[str, Any] = {
            "status": "sent", "channel": channel_id, "label": label,
        }
        if body:
            result["body"] = body
        if self.event_bus:
            await self.event_bus.emit("chat.send", {
                "agent_id": agent_id,
                "channel_id": "group_chat",
                "label": label,
                "body": body,
            })
        return result

    async def receive(
        self,
        channel_id: str,
        agent_id: str,
        timeout: float = 15.0,
    ) -> dict:
        """Wait for unread messages in group chat."""
        msgs = await self.chat.read_messages(agent_id, timeout=timeout)
        if not msgs:
            return {"status": "timeout", "channel": channel_id}
        body = _format_messages(msgs)
        if self.event_bus:
            for msg in msgs:
                await self.event_bus.emit("chat.receive", {
                    "agent_id": agent_id,
                    "from_agent": msg.sender,
                    "channel_id": f"chat_{msg.sender}",
                    "label": msg.label,
                })
        return {
            "status": "received",
            "channel": channel_id,
            "label": "chat",
            "body": body,
        }

    async def poll_channels(
        self,
        channel_ids: list[str],
        agent_id: str,
    ) -> dict:
        """Non-blocking check for unread messages."""
        unread = self.chat.consume(agent_id)
        if unread:
            body = _format_messages(unread)
            return {
                "status": "received",
                "channel": "group_chat",
                "label": "chat",
                "body": body,
            }
        return {"status": "none", "channels": channel_ids}

    async def receive_any(
        self,
        channel_ids: list[str],
        agent_id: str,
        timeout: float = 15.0,
    ) -> dict:
        """Same as receive — single chat room."""
        return await self.receive("group_chat", agent_id, timeout=timeout)

    async def acquire_lock(
        self,
        resource_id: str,
        agent_id: str,
        timeout: float = 30.0,
    ) -> dict:
        """No locks in group chat — return error."""
        return {
            "status": "error",
            "message": f"No lock support in group chat mode. "
                       f"Coordinate via chat messages instead. "
                       f"(attempted: {resource_id})",
        }

    async def release_lock(
        self,
        resource_id: str,
        agent_id: str,
    ) -> dict:
        """No locks in group chat — return error."""
        return {
            "status": "error",
            "message": f"No lock support in group chat mode. "
                       f"(attempted release: {resource_id})",
        }


# ---------------------------------------------------------------------------
# Tool schemas for OpenAI function calling
# ---------------------------------------------------------------------------

CHAT_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": (
                "Send a message to the group chat visible to all agents. "
                "Use 'label' for a short tag (e.g., 'update', 'request', "
                "'done') and 'body' for the full message content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "enum": ["group_chat"],
                        "description": "Always 'group_chat'",
                    },
                    "label": {
                        "type": "string",
                        "description": "Short message tag (e.g., 'update', 'request', 'done')",
                    },
                    "body": {
                        "type": "string",
                        "description": "Message content to send to the group chat",
                    },
                },
                "required": ["channel_id", "label", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "receive_message",
            "description": (
                "Read unread messages from the group chat. "
                "If no new messages, waits up to 15 seconds. "
                "Returns {\"status\": \"received\", \"body\": \"[sender]: message\\n...\"} "
                "with all unread messages, or {\"status\": \"timeout\"} if none arrive."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "enum": ["group_chat"],
                        "description": "Always 'group_chat'",
                    },
                },
                "required": ["channel_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "signal_done",
            "description": (
                "Signal that you have completed your work and are done. "
                "Call this when you have finished all your tasks."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


# Appended to every agent prompt with chat tool usage rules
CHAT_FOOTER = """

## Chat Tool Behavior

### send_message(channel_id="group_chat", label, body)
Sends your message to the group chat. All OTHER agents can see it.
Always succeeds. Use `label` for a short tag (e.g., 'update', 'request',
'done') and `body` for the full message content.
You will NOT see your own messages when you call receive_message.

### receive_message(channel_id="group_chat")
Returns unread messages from OTHER agents since your last read.
Your own messages are filtered out — you will never see them here.
If no new messages from others, waits up to 15 seconds.
Returns messages in the format:
  [builder_a|update]: I finished compiling Module A
  [validator|request]: Got it, I'll validate Module A

### signal_done()
When you have completed ALL your work, call signal_done() to terminate.
You MUST call signal_done() — do NOT just stop calling tools.
"""
