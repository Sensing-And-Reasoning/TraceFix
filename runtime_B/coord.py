"""CoordinationContext: shared state + async coordination operations.

Reuses MessageStore, LockStore, and CounterStore from runtime_A.store.
Each operation is validated by the ProtocolMonitor before execution.

acquire_lock / release_lock handle both Lock and Counter resources:
  - Lock: exclusive mutual exclusion — polls internally up to timeout
  - Counter: counting semaphore — polls internally up to timeout

Both acquire_lock and receive_message wait internally (with event-based
waking) so agents don't burn tool-call rounds on retry loops.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from runtime_A.store import MessageStore, LockStore, CounterStore
from runtime_B.monitor import ProtocolMonitor, ProtocolViolation

# Default timeout for coordination operations (seconds)
_DEFAULT_TIMEOUT = 30.0


class CoordinationContext:
    """Shared coordination state with async operations for agents."""

    def __init__(self, ir: dict, monitor: ProtocolMonitor, tracker=None,
                 event_bus=None):
        self.messages = MessageStore()
        self.locks = LockStore()
        self.counters = CounterStore()
        self.monitor = monitor
        self.tracker = tracker
        self.event_bus = event_bus

        # Track which resource IDs are locks vs counters
        self._lock_ids: set[str] = set()
        self._counter_ids: set[str] = set()

        # Initialize stores from IR
        for r in ir.get("resources", []):
            if r["type"] == "Lock":
                self.locks.init_lock(r["id"])
                self._lock_ids.add(r["id"])
            elif r["type"] == "Counter":
                # Support both top-level and nested config formats:
                #   {"initial_value": 2}  or  {"initial": 2}  or  {"config": {"initial": 2}}
                initial = (r.get("initial_value")
                           or r.get("initial")
                           or r.get("config", {}).get("initial", 0))
                self.counters.init_counter(r["id"], initial)
                self._counter_ids.add(r["id"])
        for ch in ir.get("channels", []):
            self.messages.init_channel(ch["id"])

        # Per-agent locks to serialize _track_and_emit for the same agent,
        # preventing state_tracker race conditions under concurrent tool calls
        self._agent_locks: dict[str, asyncio.Lock] = {
            a["id"]: asyncio.Lock() for a in ir.get("agents", [])
        }

        # Per-channel conditions for waking blocked receives (replaces Event
        # to avoid signal-loss between clear() and wait())
        self._channel_conds: dict[str, asyncio.Condition] = {
            ch["id"]: asyncio.Condition() for ch in ir.get("channels", [])
        }
        # Per-resource conditions for waking blocked acquires
        self._resource_conds: dict[str, asyncio.Condition] = {
            r["id"]: asyncio.Condition() for r in ir.get("resources", [])
        }
        # Global condition for waking receive_any waiters on any send
        self._any_send_cond = asyncio.Condition()

    async def _track_and_emit(self, agent_id: str, op_type: str, **kwargs):
        """Dispatch to tracker and emit state.transition / state.violation events.

        Uses a per-agent lock to serialize tracker mutations, preventing
        interleaved read-modify-write when concurrent tool calls (e.g.
        multiple receive_message via asyncio.gather) yield at await points.
        """
        if not self.tracker:
            return

        async with self._agent_locks[agent_id]:
            old_state = self.tracker.current_states.get(agent_id)
            old_count = self.tracker.violation_count

            if op_type == "acquire":
                self.tracker.on_acquire(agent_id, kwargs["resource_id"])
            elif op_type == "release":
                self.tracker.on_release(agent_id, kwargs["resource_id"])
            elif op_type == "send":
                self.tracker.on_send(agent_id, kwargs["channel_id"], kwargs["label"])
            elif op_type == "receive":
                self.tracker.on_receive(agent_id, kwargs["channel_id"], kwargs.get("label"))

            if not self.event_bus:
                return

            new_state = self.tracker.current_states.get(agent_id)
            if new_state != old_state:
                await self.event_bus.emit("state.transition", {
                    "agent_id": agent_id,
                    "from_state": old_state,
                    "to_state": new_state,
                    "trigger": op_type,
                })
            if self.tracker.violation_count > old_count:
                v = self.tracker.violations[-1]
                await self.event_bus.emit("state.violation", {
                    "agent_id": v.agent,
                    "current_state": v.current_state,
                    "operation": v.operation,
                    "args": v.args,
                })

    async def acquire_lock(self, resource_id: str, agent_id: str,
                           timeout: float = _DEFAULT_TIMEOUT) -> dict:
        """Acquire a resource (Lock or Counter) with internal polling.

        Polls internally with event-based waking for up to ``timeout``
        seconds.  Returns ``acquired``/``already_held`` on success, or
        ``timeout`` if the resource is still unavailable.
        """
        self.monitor.validate_acquire(agent_id, resource_id)

        if resource_id not in self._lock_ids and resource_id not in self._counter_ids:
            raise ProtocolViolation(f"Unknown resource '{resource_id}'")

        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        cond = self._resource_conds[resource_id]

        async with cond:
            while True:
                # --- try once ---
                if resource_id in self._lock_ids:
                    holder = self.locks._locks.get(resource_id)
                    if holder == agent_id:
                        return {"status": "already_held", "lock": resource_id}
                    if self.locks.try_acquire(resource_id, agent_id):
                        await self._track_and_emit(agent_id, "acquire", resource_id=resource_id)
                        return {"status": "acquired", "lock": resource_id}
                else:  # counter
                    if self.counters.try_decrement(resource_id):
                        await self._track_and_emit(agent_id, "acquire", resource_id=resource_id)
                        return {"status": "acquired", "lock": resource_id,
                                "remaining": self.counters.value(resource_id)}

                # --- check deadline ---
                remaining = deadline - loop.time()
                if remaining <= 0:
                    result = {"status": "timeout", "lock": resource_id}
                    if resource_id in self._counter_ids:
                        result["remaining"] = 0
                    return result

                # --- wait for release notification or timeout ---
                try:
                    await asyncio.wait_for(cond.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass  # loop back for one final try

    async def release_lock(self, resource_id: str, agent_id: str) -> dict:
        """Release a resource (Lock or Counter). Wakes waiting acquirers."""
        self.monitor.validate_release(agent_id, resource_id)
        await self._track_and_emit(agent_id, "release", resource_id=resource_id)

        if resource_id in self._lock_ids:
            self.locks.release(resource_id)
            cond = self._resource_conds[resource_id]
            async with cond:
                cond.notify_all()
            return {"status": "released", "lock": resource_id}

        if resource_id in self._counter_ids:
            self.counters.increment(resource_id)
            cond = self._resource_conds[resource_id]
            async with cond:
                cond.notify_all()
            return {"status": "released", "lock": resource_id,
                    "remaining": self.counters.value(resource_id)}

        raise ProtocolViolation(f"Unknown resource '{resource_id}'")

    async def send(self, channel_id: str, label: str,
                   agent_id: str, body: str = "") -> dict:
        """Send a labeled message. Non-blocking (unbounded FIFO)."""
        self.monitor.validate_send(agent_id, channel_id, label)
        await self._track_and_emit(agent_id, "send", channel_id=channel_id, label=label)
        self.messages.send(channel_id, label, agent_id, body=body)
        cond = self._channel_conds[channel_id]
        async with cond:
            cond.notify_all()
        # Wake any receive_any waiters listening across channels
        async with self._any_send_cond:
            self._any_send_cond.notify_all()
        result = {"status": "sent", "channel": channel_id, "label": label}
        if body:
            result["body"] = body
        return result

    async def receive(self, channel_id: str, agent_id: str,
                      timeout: float = _DEFAULT_TIMEOUT) -> dict:
        """Wait for a message with timeout.

        Returns {"status": "received", "label": ...} if a message arrives,
        or {"status": "timeout"} if no message within timeout seconds.
        """
        self.monitor.validate_receive(agent_id, channel_id)
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        cond = self._channel_conds[channel_id]

        async with cond:
            while True:
                msgs = self.messages._channels.get(channel_id, [])
                if msgs:
                    msg = msgs.pop(0)
                    await self._track_and_emit(agent_id, "receive", channel_id=channel_id, label=msg.label)
                    result = {"status": "received", "channel": channel_id,
                              "label": msg.label}
                    if msg.body:
                        result["body"] = msg.body
                    return result
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return {"status": "timeout", "channel": channel_id}
                try:
                    await asyncio.wait_for(cond.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass  # loop back for one final check

    async def poll_channels(self, channel_ids: list[str],
                            agent_id: str) -> dict:
        """Non-blocking poll: check multiple channels for pending messages.

        Returns the first pending message found, or {"status": "none"}.
        Maps to PlusCal either/or where receive branches coexist with
        always-enabled branches (send/goto).
        """
        for ch_id in channel_ids:
            self.monitor.validate_receive(agent_id, ch_id)

        for ch_id in channel_ids:
            msgs = self.messages._channels.get(ch_id, [])
            if msgs:
                msg = msgs.pop(0)
                await self._track_and_emit(agent_id, "receive",
                                           channel_id=ch_id, label=msg.label)
                result = {"status": "received", "channel": ch_id,
                          "label": msg.label}
                if msg.body:
                    result["body"] = msg.body
                return result

        return {"status": "none", "channels": channel_ids}

    async def receive_any(self, channel_ids: list[str], agent_id: str,
                          timeout: float = _DEFAULT_TIMEOUT) -> dict:
        """Wait for a message on any of the given channels.

        Returns the first message received from any channel.
        Uses a global send condition to wake up when any send occurs.
        Maps to PlusCal either/or where all branches are receives.
        """
        for ch_id in channel_ids:
            self.monitor.validate_receive(agent_id, ch_id)

        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout

        async with self._any_send_cond:
            while True:
                # Check all channels for pending messages
                for ch_id in channel_ids:
                    msgs = self.messages._channels.get(ch_id, [])
                    if msgs:
                        msg = msgs.pop(0)
                        await self._track_and_emit(
                            agent_id, "receive",
                            channel_id=ch_id, label=msg.label)
                        result = {"status": "received", "channel": ch_id,
                                  "label": msg.label}
                        if msg.body:
                            result["body"] = msg.body
                        return result

                remaining = deadline - loop.time()
                if remaining <= 0:
                    return {"status": "timeout", "channels": channel_ids}

                try:
                    await asyncio.wait_for(
                        self._any_send_cond.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass  # loop back for one final check


# ---------------------------------------------------------------------------
# Tool schemas for OpenAI function calling
# ---------------------------------------------------------------------------

COORD_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "acquire_lock",
            "description": "Acquire a resource (lock or counter slot). Waits internally for up to 30 seconds. Returns {\"status\": \"acquired\"} on success, {\"status\": \"timeout\"} if still unavailable after 30s, or {\"status\": \"already_held\"} if you already hold this lock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lock_id": {"type": "string", "description": "ID of the resource to acquire"}
                },
                "required": ["lock_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "release_lock",
            "description": "Release a resource (lock or counter slot) you currently hold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lock_id": {"type": "string", "description": "ID of the resource to release"}
                },
                "required": ["lock_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send a labeled message on a channel. Non-blocking. Optionally include a body with additional content (e.g. data, results, instructions).",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string", "description": "ID of the channel"},
                    "label": {"type": "string", "description": "Message label (e.g. 'submit', 'pass', 'flag')"},
                    "body": {"type": "string", "description": "Optional message body with additional content"},
                },
                "required": ["channel_id", "label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "receive_message",
            "description": "Wait for a message on a channel. If a message is already pending, returns it immediately. Otherwise waits up to 30 seconds. Returns {\"status\": \"received\", \"label\": ...} on success, or {\"status\": \"timeout\"} if no message arrives in time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string", "description": "ID of the channel"},
                },
                "required": ["channel_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "poll_channels",
            "description": "Non-blocking check for pending messages on multiple channels. Returns the first message found immediately, or {\"status\": \"none\"} if no messages are pending. Use this when you have a default action to take if no messages are waiting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of channel IDs to check for pending messages",
                    },
                },
                "required": ["channel_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "receive_any",
            "description": "Wait for a message on any of the given channels. Returns the first message that arrives. If no message arrives within 30 seconds, returns {\"status\": \"timeout\"}. Use this when you need to wait for a message from one of several possible senders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of channel IDs to wait on simultaneously",
                    },
                },
                "required": ["channel_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "signal_done",
            "description": "Signal that you have completed your protocol and are done. Call this when you reach your final step.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
