"""CoordBackend: the seam between consumers and the coordination implementation.

Every runtime consumer (sdk_adapter/dispatch.py, monitoring/agent_runner.py) talks
to coordination through exactly these async methods on a ``self.coord`` object.
Both the in-process ``CoordinationContext`` (shared memory) and the network
``CoordClient`` (RPC to a CoordinationService) satisfy this Protocol, so making
the MAS distributed is just handing each agent's dispatcher a ``CoordClient``
instead of a shared ``CoordinationContext``.

There is already a de-facto precedent: ``baselines/shared_chat/chat_coord.py``
duck-types these same methods and ``AgentRunner`` consumes it unchanged. This
Protocol formalizes that interface.
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
                   body: str = "") -> dict: ...

    async def receive(self, channel_id: str, agent_id: str,
                      timeout: float = DEFAULT_TIMEOUT) -> dict: ...

    async def poll_channels(self, channel_ids: list[str], agent_id: str) -> dict: ...

    async def receive_any(self, channel_ids: list[str], agent_id: str,
                          timeout: float = DEFAULT_TIMEOUT) -> dict: ...

    async def get_held_locks(self, agent_id: str) -> list[str]: ...
