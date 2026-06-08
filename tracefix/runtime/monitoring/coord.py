"""CoordinationContext: shared state + async coordination operations.

Reuses MessageStore, LockStore, and CounterStore from tracefix.runtime.store.
Each operation is validated by the ProtocolMonitor before execution.

acquire_lock / release_lock handle both Lock and Counter resources:
  - Lock: exclusive mutual exclusion — polls internally up to timeout
  - Counter: counting semaphore — polls internally up to timeout

Both acquire_lock and receive_message wait internally (with event-based
waking) so agents don't burn tool-call rounds on retry loops.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from tracefix.runtime.store import MessageStore, LockStore, CounterStore, ConversationStore
from tracefix.runtime.monitoring.monitor import (
    ProtocolMonitor, ProtocolViolation, StateGuidanceError)

# Default timeout for coordination operations (seconds)
_DEFAULT_TIMEOUT = 30.0


class CoordinationContext:
    """Shared coordination state with async operations for agents."""

    def __init__(self, ir: dict, monitor: ProtocolMonitor, tracker=None,
                 event_bus=None, correction: bool = False):
        self.messages = MessageStore()
        self.locks = LockStore()
        self.counters = CounterStore()
        # Data plane: business content lives here (the claim-check target), never on
        # a channel. An agent post_content()s here, gets an opaque ref, and may send
        # that ref only on a content-carrying label (gated in send()).
        self.conversations = ConversationStore()
        self.monitor = monitor
        self.tracker = tracker
        self.event_bus = event_bus
        # When True, an out-of-order coordination op is BLOCKED (pre-effect) and
        # raised as StateGuidanceError with the legal next actions, instead of
        # being soft-recorded after the fact. Off by default so bare contexts
        # (and existing tests) keep today's behavior.
        self.correction = correction
        # Observability plane: optional progress beacons reported by agents via
        # report_progress(). Pure telemetry — never validated, never a violation.
        self.beacons: list[dict] = []

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
        # Per-channel set of labels that carry business content. The control plane
        # "opens" the content channel ONLY on these (e.g. 'revise'); every other
        # label is a pure signal and a content ref is rejected (default-closed).
        self._content_labels: dict[str, set[str]] = {}
        for ch in ir.get("channels", []):
            self.messages.init_channel(ch["id"])
            self._content_labels[ch["id"]] = set(ch.get("content_labels", []))

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

    def _guard(self, agent_id: str, op_type: str, op_args: dict) -> None:
        """Pre-check the state machine; raise StateGuidanceError if the op is
        out of order. No-op unless correction mode is on and a tracker exists.

        Synchronous + read-only (``check_op`` snapshots/restores), so it runs
        atomically before the operation's effect/await.
        """
        if not (self.correction and self.tracker):
            return
        ok, legal = self.tracker.check_op(agent_id, op_type, op_args)
        if not ok:
            raise StateGuidanceError(
                agent_id, op_type, op_args, legal,
                context=self._situational_context(agent_id, op_type, op_args))

    def _situational_context(self, agent_id: str, op_type: str,
                             op_args: dict) -> str:
        """Best-effort hint from current store state to aid recovery."""
        if op_type == "acquire":
            res = op_args.get("resource")
            holder = self.locks._locks.get(res) if res in self._lock_ids else None
            if holder and holder != "FREE":
                return f"{res} is currently held by {holder}"
        # Pending messages the agent may need to receive first.
        waiting = [ch for ch in self.monitor._receive_whitelist.get(agent_id, set())
                   if self.messages._channels.get(ch)]
        if waiting:
            return f"unread message(s) waiting on channel(s): {', '.join(sorted(waiting))}"
        return ""

    def _guard_any(self, agent_id: str, channel_ids: list[str]) -> None:
        """Guard a multi-channel poll/receive_any: legal iff at least one of the
        polled channels is a receivable channel at the agent's current state."""
        if not (self.correction and self.tracker):
            return
        legal = self.tracker.legal_actions(agent_id)
        legal_recv = {h.get("channel") for h in legal if h.get("op") == "receive"}
        if legal_recv & set(channel_ids):
            return
        # None of the polled channels is receivable now — record one violation + block.
        self.tracker.check_op(agent_id, "receive", {"channel": channel_ids[0]})
        raise StateGuidanceError(
            agent_id, "receive", {"channel": ",".join(channel_ids)}, legal,
            context=self._situational_context(agent_id, "receive", {}))

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
            old_phase = self.tracker.current_phases.get(agent_id)
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
            new_phase = self.tracker.current_phases.get(agent_id)
            if new_phase != old_phase:
                await self.event_bus.emit("agent.phase", {
                    "agent_id": agent_id,
                    "from_phase": old_phase,
                    "to_phase": new_phase,
                    "task": (self.tracker.state_tasks.get(new_phase)
                             if new_phase else None),
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
        self._guard(agent_id, "acquire", {"resource": resource_id})

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
        self._guard(agent_id, "release", {"resource": resource_id})
        # Owner check (H2): a Lock may only be released by its current holder.
        # validate_release only checks agent/resource existence, and the Lock branch
        # below calls store.release() with no agent_id, so without this a non-holder's
        # topologically/FSM-legal release would SILENTLY free another agent's lock —
        # breaking mutual exclusion (a safety property TLC proved). Raise BEFORE
        # _track_and_emit so a rejected release never advances the state machine;
        # ProtocolViolation is caught by both runtimes' dispatchers. Counters have no
        # holder concept and are exempt.
        if (resource_id in self._lock_ids
                and self.locks._locks.get(resource_id) != agent_id):
            holder = self.locks._locks.get(resource_id)
            raise ProtocolViolation(
                f"{agent_id} cannot release lock '{resource_id}' "
                f"(held by {holder or 'nobody'})")
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

    async def send(self, channel_id: str, label: str, agent_id: str,
                   ref: str | None = None) -> dict:
        """Send a labeled message. Non-blocking (unbounded FIFO).

        Channels are flag-only. The only data a send may carry is an opaque content
        ``ref`` (a claim-check handle from post_content), and ONLY on a label the IR
        declared content-carrying — the control plane gates this: a ref on a pure
        signal label is rejected, and a content-carrying label requires one. Business
        payload never rides the channel; it lives in the ConversationStore (data plane).
        """
        self.monitor.validate_send(agent_id, channel_id, label)
        self._guard(agent_id, "send", {"channel": channel_id, "label": label})
        # Content-channel gate (default-closed): a ref may ride ONLY a content label.
        carries_content = label in self._content_labels.get(channel_id, set())
        if ref:
            if not carries_content:
                raise ProtocolViolation(
                    f"label '{label}' on '{channel_id}' is a pure signal — content "
                    f"channel is closed; no ref allowed (declare it in the channel's "
                    f"content_labels to carry content)")
            if ref not in self.conversations:
                raise ProtocolViolation(f"unknown content ref '{ref}'")
        elif carries_content:
            raise ProtocolViolation(
                f"label '{label}' on '{channel_id}' carries content — attach a `ref` "
                f"from post_content() (the payload travels on the data plane)")
        await self._track_and_emit(agent_id, "send", channel_id=channel_id, label=label)
        self.messages.send(channel_id, label, agent_id, ref=ref or "")
        cond = self._channel_conds[channel_id]
        async with cond:
            cond.notify_all()
        # Wake any receive_any waiters listening across channels
        async with self._any_send_cond:
            self._any_send_cond.notify_all()
        result = {"status": "sent", "channel": channel_id, "label": label}
        if ref:
            result["ref"] = ref
        return result

    async def receive(self, channel_id: str, agent_id: str,
                      timeout: float = _DEFAULT_TIMEOUT) -> dict:
        """Wait for a message with timeout.

        Returns {"status": "received", "label": ...} if a message arrives,
        or {"status": "timeout"} if no message within timeout seconds.
        """
        self.monitor.validate_receive(agent_id, channel_id)
        self._guard(agent_id, "receive", {"channel": channel_id})
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
                    if msg.ref:
                        result["ref"] = msg.ref
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
        self._guard_any(agent_id, channel_ids)

        for ch_id in channel_ids:
            msgs = self.messages._channels.get(ch_id, [])
            if msgs:
                msg = msgs.pop(0)
                await self._track_and_emit(agent_id, "receive",
                                           channel_id=ch_id, label=msg.label)
                result = {"status": "received", "channel": ch_id,
                          "label": msg.label}
                if msg.ref:
                    result["ref"] = msg.ref
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
        self._guard_any(agent_id, channel_ids)

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
                        if msg.ref:
                            result["ref"] = msg.ref
                        return result

                remaining = deadline - loop.time()
                if remaining <= 0:
                    return {"status": "timeout", "channels": channel_ids}

                try:
                    await asyncio.wait_for(
                        self._any_send_cond.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass  # loop back for one final check

    async def get_held_locks(self, agent_id: str) -> list[str]:
        """Lock resources currently held by ``agent_id``.

        Replaces consumers reaching into ``self.locks._locks`` directly (e.g. the
        orphan-lock check at signal_done in sdk_adapter/dispatch.py), so the
        coordination interface is uniform across the in-process context and the
        network CoordClient — see tracefix.runtime.coordination.CoordBackend.
        """
        return [lid for lid, holder in self.locks._locks.items()
                if holder == agent_id]

    async def signal_done(self, agent_id: str) -> dict:
        """Authoritative termination check (H3) — uniform in-process and over the wire.

        A done is ALLOWED only from a state that can still reach a terminal state
        (``tracker.can_terminate`` follows skip chains, so a domain/business tail does
        NOT falsely block it). This stops a content message ("we're done, signal done")
        from terminating an agent that still owes a coordination op and stranding peers
        blocked on a label that never arrives (liveness).

        Because the StateTracker lives wherever the CoordinationContext lives, routing
        signal_done through this method gives the distributed
        (CoordClient → CoordinationService) path the SAME FSM gate the in-process
        runtimes get — not just the held-locks fallback. It returns a result dict and
        does NOT mutate dispatcher state (the caller maps ``status``/``warning`` onto
        its own done / premature_done flags).
        """
        if self.tracker is not None and not self.tracker.can_terminate(agent_id):
            return {"status": "error", "error": "cannot_terminate",
                    "message": ("Cannot signal_done yet: the coordination protocol has "
                                "remaining obligations. Continue your protocol steps.")}
        held = await self.get_held_locks(agent_id)
        result = {"status": "done", "agent": agent_id}
        if held:
            result["held_locks"] = held
            result["warning"] = (f"signal_done while still holding lock(s) {held} — "
                                 f"coordination incomplete (orphan-lock risk)")
        return result

    async def report_progress(self, label: str, agent_id: str) -> dict:
        """Observability-plane telemetry: record a business-progress beacon.

        Deliberately bypasses the control plane — it calls NONE of the monitor, the
        state-machine guard, or the tracker, so it can never be a violation or a
        correction and never touches coordination state. It only appends a beacon
        and (if a live bus is attached) emits an ``agent.progress`` event.
        """
        self.beacons.append({"agent": agent_id, "label": label, "ts": time.time()})
        if self.event_bus is not None:
            await self.event_bus.emit("agent.progress", {
                "agent_id": agent_id, "label": label,
            })
        return {"status": "ok", "label": label}

    async def post_content(self, content: str, agent_id: str,
                           content_type: str = "text") -> dict:
        """Data-plane: store business content; return its opaque claim-check ref.

        Bypasses the control plane entirely (no monitor / guard / tracker) — content
        is data, never a coordination op. The ref becomes visible to a peer only if
        the agent later sends it on a content-carrying label (gated in send()).
        """
        entry = self.conversations.put(agent_id, content, content_type=content_type)
        return {"status": "ok", "ref": entry.ref, "content_type": entry.content_type}

    async def get_content(self, ref: str, agent_id: str) -> dict:
        """Data-plane: resolve a content ref to its payload (no control-plane check)."""
        entry = self.conversations.get(ref)
        if entry is None:
            return {"status": "not_found", "ref": ref}
        return {"status": "ok", "ref": ref, "sender": entry.sender,
                "content_type": entry.content_type, "content": entry.content}


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
            "description": "Send a labeled message on a channel. Non-blocking. Channels carry a finite LABEL only. On a content-carrying label (e.g. 'revise') attach `ref` (an opaque handle from post_content) to deliver business content on the data plane; on a pure-signal label (e.g. 'accept'/'ready') send no ref.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string", "description": "ID of the channel"},
                    "label": {"type": "string", "description": "Message label (e.g. 'submit', 'pass', 'flag')"},
                    "ref": {"type": "string", "description": "Opaque content handle from post_content; attach ONLY on a content-carrying label. Rejected on pure-signal labels; required on content labels."},
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
    {
        "type": "function",
        "function": {
            "name": "report_progress",
            "description": "OPTIONAL progress beacon. Announce a finer-grained business sub-phase you are currently working on (e.g. 'reading_research', 'generating_figure', 'saving'). This is telemetry ONLY — it is never required, never affects coordination or correctness, and can never be out of order. Use it sparingly to make your progress observable.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Short business sub-phase label"},
                },
                "required": ["label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "post_content",
            "description": "Data-plane (NOT coordination): store business content (e.g. your revision suggestions, a result) and get back an opaque `ref`. The content does NOT move yet — attach the ref to a send_message on a content-carrying label so the receiver can read it with get_content. Never affects coordination or verification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The business content to store"},
                    "content_type": {"type": "string", "description": "Optional type tag (e.g. 'review', 'result', 'text')"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_content",
            "description": "Data-plane (NOT coordination): resolve a content `ref` (received on a content-carrying message) to its payload. Never affects coordination or verification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "description": "The opaque content handle received on a message"},
                },
                "required": ["ref"],
            },
        },
    },
]
