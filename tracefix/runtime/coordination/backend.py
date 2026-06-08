"""CoordBackend: the seam between consumers and the coordination implementation.

Every runtime consumer (sdk_adapter/dispatch.py, monitoring/agent_runner.py) talks
to coordination through exactly these async methods on a ``self.coord`` object.
Both the in-process ``CoordinationContext`` (shared memory) and the network
``CoordClient`` (RPC to a CoordinationService) satisfy this Protocol, so making
the MAS distributed is just handing each agent's dispatcher a ``CoordClient``
instead of a shared ``CoordinationContext``.

The in-process ``CoordinationContext`` already satisfies these methods; this
Protocol formalizes that interface so the network ``CoordClient`` is a drop-in.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# Default coordination op timeout (mirrors coord._DEFAULT_TIMEOUT; kept as a literal
# here so this pure-interface module doesn't import the implementation).
DEFAULT_TIMEOUT = 30.0


@runtime_checkable
class CoordBackend(Protocol):
    """The 6 coordination operations + one accessor every consumer depends on.

    All async, all return plain dicts (network-ready). ``agent_id`` is always passed
    by the caller (the dispatcher binds it). ``get_held_locks`` replaces the only
    place a consumer reached past this interface into store internals
    (``coord.locks._locks`` at sdk_adapter/dispatch.py).
    """

    async def acquire_lock(self, resource_id: str, agent_id: str,
                           timeout: float = DEFAULT_TIMEOUT) -> dict: ...

    async def release_lock(self, resource_id: str, agent_id: str) -> dict: ...

    async def send(self, channel_id: str, label: str, agent_id: str,
                   ref: str | None = None) -> dict: ...

    async def receive(self, channel_id: str, agent_id: str,
                      timeout: float = DEFAULT_TIMEOUT) -> dict: ...

    async def poll_channels(self, channel_ids: list[str], agent_id: str) -> dict: ...

    async def receive_any(self, channel_ids: list[str], agent_id: str,
                          timeout: float = DEFAULT_TIMEOUT) -> dict: ...

    async def get_held_locks(self, agent_id: str) -> list[str]: ...

    # H3 termination gate: allowed only from a state that can still reach a
    # terminal state (the tracker, wherever it lives, is authoritative).
    async def signal_done(self, agent_id: str) -> dict: ...

    # Data plane (claim-check): store business content, return an opaque ref; and
    # resolve a ref to its payload. Bypasses the monitor — content is never a
    # coordination op. Networked so a ref posted by one node resolves on another.
    async def post_content(self, content: str, agent_id: str,
                           content_type: str = "text") -> dict: ...

    async def get_content(self, ref: str, agent_id: str) -> dict: ...

    # Observability-plane telemetry (non-enforced): record a business-progress
    # beacon. Never validated, never a violation; both backends implement it.
    async def report_progress(self, label: str, agent_id: str) -> dict: ...
