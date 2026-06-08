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
    ref: str = ""  # opaque claim-check handle into ConversationStore (data plane)


class MessageStore:
    """In-memory channel message store (swarm-ide uses PostgreSQL messages table)."""

    def __init__(self):
        self._channels: dict[str, list[StoredMessage]] = {}
        self._next_id = 0
        self._t0 = time.monotonic()

    def init_channel(self, channel_id: str):
        self._channels[channel_id] = []

    def send(self, channel: str, label: str, sender: str,
             ref: str = "") -> StoredMessage:
        """Append a labeled message. Non-blocking, always succeeds (unbounded).

        Channels are flag-only: a message carries a ``label`` (a signal) and an
        optional opaque content ``ref`` (claim-check). Business payload never rides
        the channel — it lives in the ConversationStore (data plane).
        """
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
            ref=ref,
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


# ---------------------------------------------------------------------------
# Conversation Store (data-plane business content)
# ---------------------------------------------------------------------------

@dataclass
class ContentEntry:
    ref: str
    sender: str
    content_type: str
    content: str
    timestamp: float


class ConversationStore:
    """In-memory data-plane store for business content — the claim-check target.

    Business content NEVER rides a verified channel. An agent ``put``s content here
    and gets back an opaque ``ref``; only that small ref crosses a coordination
    channel, and only on a content-carrying label (the control plane gates this).
    The receiver resolves the ref with ``get``. Entries are append-only and
    immutable; refs are opaque tokens carrying no addressing or identity in their
    surface form. In-memory by default — the same put/get interface can be backed
    by Redis or an object store for a distributed/large-payload data plane, without
    touching the control plane.
    """

    def __init__(self):
        self._entries: dict[str, ContentEntry] = {}
        self._next_id = 0
        self._t0 = time.monotonic()

    def put(self, sender: str, content: str, content_type: str = "text") -> ContentEntry:
        """Store one content entry; return it (its ``ref`` is the opaque handle)."""
        ref = f"cs_{self._next_id}"
        self._next_id += 1
        entry = ContentEntry(
            ref=ref, sender=sender, content_type=content_type,
            content=content, timestamp=time.monotonic() - self._t0,
        )
        self._entries[ref] = entry
        return entry

    def get(self, ref: str) -> ContentEntry | None:
        """Resolve a ref to its entry, or None if unknown."""
        return self._entries.get(ref)

    def __contains__(self, ref: str) -> bool:
        return ref in self._entries
