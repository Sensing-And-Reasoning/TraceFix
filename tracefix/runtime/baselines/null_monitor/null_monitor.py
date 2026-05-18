"""NullMonitor: relaxed monitor that only checks resource/channel existence.

Duck-type compatible with ProtocolMonitor — can be passed directly to
CoordinationContext. Does NOT validate topology whitelists (any agent can
use any channel/resource as long as it exists in the IR).
"""

from __future__ import annotations

from dataclasses import dataclass

from tracefix.runtime.monitoring.monitor import ProtocolViolation, TraceEntry


class NullMonitor:
    """Validates only that resources and channels exist (no topology checks)."""

    def __init__(self, ir: dict):
        self._agents: set[str] = {a["id"] for a in ir["agents"]}
        self._resources: set[str] = {r["id"] for r in ir.get("resources", [])}
        self._channels: set[str] = {ch["id"] for ch in ir.get("channels", [])}
        self._channel_labels: dict[str, set[str]] = {
            ch["id"]: set(ch.get("labels", []))
            for ch in ir.get("channels", [])
        }
        self._trace: list[TraceEntry] = []

    @property
    def trace(self) -> list[TraceEntry]:
        return list(self._trace)

    def _record(self, agent: str, operation: str, target: str,
                label: str | None = None):
        self._trace.append(TraceEntry(agent, operation, target, label))

    def validate_send(self, agent_id: str, channel_id: str,
                      label: str | None = None) -> bool:
        if channel_id not in self._channels:
            raise ProtocolViolation(
                f"Channel '{channel_id}' does not exist")
        valid_labels = self._channel_labels.get(channel_id, set())
        if valid_labels and label and label not in valid_labels:
            raise ProtocolViolation(
                f"Label '{label}' not valid for channel '{channel_id}' "
                f"(valid: {sorted(valid_labels)})")
        self._record(agent_id, "send", channel_id, label)
        return True

    def validate_receive(self, agent_id: str, channel_id: str) -> bool:
        if channel_id not in self._channels:
            raise ProtocolViolation(
                f"Channel '{channel_id}' does not exist")
        self._record(agent_id, "receive", channel_id)
        return True

    def validate_acquire(self, agent_id: str, resource_id: str) -> bool:
        if resource_id not in self._resources:
            raise ProtocolViolation(
                f"Resource '{resource_id}' does not exist")
        self._record(agent_id, "acquire", resource_id)
        return True

    def validate_release(self, agent_id: str, resource_id: str) -> bool:
        if resource_id not in self._resources:
            raise ProtocolViolation(
                f"Resource '{resource_id}' does not exist")
        self._record(agent_id, "release", resource_id)
        return True
