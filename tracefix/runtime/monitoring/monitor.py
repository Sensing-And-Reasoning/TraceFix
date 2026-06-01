"""ProtocolMonitor: validates coordination operations against IR topology.

The monitor builds whitelists from the IR and checks every send/receive/
acquire/release call.  Invalid operations raise ``ProtocolViolation``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ProtocolViolation(Exception):
    """Raised when an agent attempts an operation not allowed by the IR."""


class StateGuidanceError(ProtocolViolation):
    """A coordination op that is illegal at the agent's CURRENT state (out of
    order), carrying corrective guidance.

    Subclasses ``ProtocolViolation`` so existing ``except ProtocolViolation``
    handlers still catch it; consumers that want the guidance read the extra
    attributes (``legal_actions``, ``context``) or rebuild a rich message via
    ``tracefix.runtime.monitoring.correction.corrective_result``.
    """

    def __init__(self, agent_id: str, op_type: str, op_args: dict,
                 legal_actions: list[dict], context: str = ""):
        self.agent_id = agent_id
        self.op_type = op_type
        self.op_args = op_args
        self.legal_actions = legal_actions
        self.context = context
        target = op_args.get("resource") or op_args.get("channel") or ""
        super().__init__(
            f"Agent '{agent_id}' cannot {op_type} '{target}' at its current "
            f"protocol step (out of order).")


@dataclass
class TraceEntry:
    agent: str
    operation: str  # "send" | "receive" | "acquire" | "release"
    target: str     # channel_id or lock_id
    label: str | None = None


class ProtocolMonitor:
    """Validate coordination operations against the IR topology definition."""

    def __init__(self, ir: dict):
        self._agents: set[str] = {a["id"] for a in ir["agents"]}
        self._locks: set[str] = set()
        self._counters: set[str] = set()
        for r in ir.get("resources", []):
            if r["type"] == "Lock":
                self._locks.add(r["id"])
            elif r["type"] == "Counter":
                self._counters.add(r["id"])

        # Build send/receive whitelists from channels
        self._send_whitelist: dict[str, set[str]] = {}    # agent → {channel_ids}
        self._receive_whitelist: dict[str, set[str]] = {}  # agent → {channel_ids}
        self._channel_labels: dict[str, set[str]] = {}     # channel → {valid labels}

        for ch in ir.get("channels", []):
            ch_id = ch["id"]
            labels = set(ch.get("labels", []))
            self._channel_labels[ch_id] = labels

            # from agent(s) can send
            from_agent = ch["from"]
            from_agents = [from_agent] if isinstance(from_agent, str) else from_agent
            for a in from_agents:
                self._send_whitelist.setdefault(a, set()).add(ch_id)

            # to agent(s) can receive
            to_agent = ch["to"]
            to_agents = [to_agent] if isinstance(to_agent, str) else to_agent
            for a in to_agents:
                self._receive_whitelist.setdefault(a, set()).add(ch_id)

        self._trace: list[TraceEntry] = []

    @property
    def trace(self) -> list[TraceEntry]:
        return list(self._trace)

    def _record(self, agent: str, operation: str, target: str,
                label: str | None = None):
        self._trace.append(TraceEntry(agent, operation, target, label))

    def validate_send(self, agent_id: str, channel_id: str,
                      label: str | None = None) -> bool:
        if agent_id not in self._agents:
            raise ProtocolViolation(
                f"Unknown agent '{agent_id}'")
        allowed = self._send_whitelist.get(agent_id, set())
        if channel_id not in allowed:
            raise ProtocolViolation(
                f"Agent '{agent_id}' cannot send on channel '{channel_id}'")
        valid_labels = self._channel_labels.get(channel_id, set())
        if valid_labels and label and label not in valid_labels:
            raise ProtocolViolation(
                f"Label '{label}' not valid for channel '{channel_id}' "
                f"(valid: {sorted(valid_labels)})")
        self._record(agent_id, "send", channel_id, label)
        return True

    def validate_receive(self, agent_id: str, channel_id: str) -> bool:
        if agent_id not in self._agents:
            raise ProtocolViolation(
                f"Unknown agent '{agent_id}'")
        allowed = self._receive_whitelist.get(agent_id, set())
        if channel_id not in allowed:
            raise ProtocolViolation(
                f"Agent '{agent_id}' cannot receive on channel '{channel_id}'")
        self._record(agent_id, "receive", channel_id)
        return True

    def validate_acquire(self, agent_id: str, resource_id: str) -> bool:
        if agent_id not in self._agents:
            raise ProtocolViolation(
                f"Unknown agent '{agent_id}'")
        if resource_id not in self._locks and resource_id not in self._counters:
            raise ProtocolViolation(
                f"Unknown resource '{resource_id}'")
        self._record(agent_id, "acquire", resource_id)
        return True

    def validate_release(self, agent_id: str, resource_id: str) -> bool:
        if agent_id not in self._agents:
            raise ProtocolViolation(
                f"Unknown agent '{agent_id}'")
        if resource_id not in self._locks and resource_id not in self._counters:
            raise ProtocolViolation(
                f"Unknown resource '{resource_id}'")
        self._record(agent_id, "release", resource_id)
        return True
