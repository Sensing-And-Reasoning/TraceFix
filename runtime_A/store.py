"""Swarm-IDE style in-memory stores for messages, locks, and counters.

Mirrors swarm-ide's PostgreSQL-backed storage but uses in-memory data structures.
All operations are synchronous and non-blocking (no await).
Atomicity is guaranteed by asyncio's cooperative scheduling — callers never
yield (await) between check and mutate, so no interleaving occurs.
"""

import time
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Message Store
# ---------------------------------------------------------------------------

@dataclass
class StoredMessage:
    id: int
    channel: str
    label: str
    sender: str
    timestamp: float
    body: str = ""


class MessageStore:
    """In-memory channel message store (swarm-ide uses PostgreSQL messages table)."""

    def __init__(self):
        self._channels: dict[str, list[StoredMessage]] = {}
        self._next_id = 0
        self._t0 = time.monotonic()

    def init_channel(self, channel_id: str):
        self._channels[channel_id] = []

    def send(self, channel: str, label: str, sender: str,
             body: str = "") -> StoredMessage:
        """Append a labeled message. Non-blocking, always succeeds (unbounded)."""
        if channel not in self._channels:
            raise KeyError(
                f"Channel '{channel}' not initialized — call init_channel() first"
            )
        msg = StoredMessage(
            id=self._next_id,
            channel=channel,
            label=label,
            sender=sender,
            timestamp=time.monotonic() - self._t0,
            body=body,
        )
        self._channels[channel].append(msg)
        self._next_id += 1
        return msg

    def peek(self, channel: str, label: str | None) -> bool:
        """Check if a matching message exists. Read-only, no mutation.
        If label is None, matches any message in the channel."""
        msgs = self._channels.get(channel, [])
        if label is None:
            return len(msgs) > 0
        return any(m.label == label for m in msgs)

    def try_consume(self, channel: str, label: str | None) -> StoredMessage | None:
        """Find and remove first message with matching label (selective receive).
        If label is None, consumes the first message regardless of label."""
        msgs = self._channels.get(channel, [])
        if label is None and msgs:
            return msgs.pop(0)
        for i, m in enumerate(msgs):
            if m.label == label:
                return msgs.pop(i)
        return None


# ---------------------------------------------------------------------------
# Lock Store
# ---------------------------------------------------------------------------

class LockStore:
    """In-memory lock store. Each lock is free (None) or held by an agent."""

    def __init__(self):
        self._locks: dict[str, str | None] = {}  # lock_id → holder or None

    def init_lock(self, lock_id: str):
        self._locks[lock_id] = None

    def is_free(self, lock_id: str) -> bool:
        return self._locks.get(lock_id) is None

    def try_acquire(self, lock_id: str, agent_id: str) -> bool:
        """Try to acquire. Returns True if successful, False if held."""
        if self._locks.get(lock_id) is None:
            self._locks[lock_id] = agent_id
            return True
        return False

    def release(self, lock_id: str, agent_id: str | None = None):
        """Release a lock.  If agent_id is given, asserts the caller holds it."""
        if agent_id is not None and self._locks.get(lock_id) != agent_id:
            holder = self._locks.get(lock_id)
            raise RuntimeError(
                f"Agent '{agent_id}' cannot release lock '{lock_id}' "
                f"(held by '{holder}')"
            )
        self._locks[lock_id] = None

    def __contains__(self, lock_id: str) -> bool:
        return lock_id in self._locks


# ---------------------------------------------------------------------------
# Counter Store
# ---------------------------------------------------------------------------

class CounterStore:
    """In-memory counter store. Counters are non-negative integers."""

    def __init__(self):
        self._counters: dict[str, int] = {}

    def init_counter(self, counter_id: str, initial: int):
        self._counters[counter_id] = initial

    def value(self, counter_id: str) -> int:
        return self._counters.get(counter_id, 0)

    def try_decrement(self, counter_id: str) -> bool:
        """Decrement if > 0. Returns True if successful."""
        if self._counters.get(counter_id, 0) > 0:
            self._counters[counter_id] -= 1
            return True
        return False

    def increment(self, counter_id: str):
        if counter_id not in self._counters:
            raise KeyError(
                f"Counter '{counter_id}' not initialized — call init_counter() first"
            )
        self._counters[counter_id] += 1

    def __contains__(self, counter_id: str) -> bool:
        return counter_id in self._counters
