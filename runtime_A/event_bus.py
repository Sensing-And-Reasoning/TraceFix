"""Async event bus for real-time visualization.

Uses one asyncio.Queue per SSE subscriber. Events are broadcast
to all connected clients without blocking the agent execution loop.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field


@dataclass
class Event:
    type: str
    data: dict
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        """Format as SSE message: 'event: <type>\ndata: <json>\n\n'."""
        payload = {**self.data, "_ts": self.timestamp}
        return f"event: {self.type}\ndata: {json.dumps(payload)}\n\n"


class EventBus:
    """Broadcast events to all SSE subscribers."""

    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()

    async def emit(self, event_type: str, data: dict | None = None):
        """Broadcast an event to all subscribers (non-blocking)."""
        event = Event(type=event_type, data=data or {})
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)

    async def subscribe(self):
        """Async generator yielding SSE-formatted strings."""
        q: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        try:
            while True:
                event = await q.get()
                if event is None:
                    break
                yield event.to_sse()
        finally:
            self._subscribers.discard(q)

    async def close(self):
        """Signal all subscribers to disconnect."""
        for q in list(self._subscribers):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
        self._subscribers.clear()
