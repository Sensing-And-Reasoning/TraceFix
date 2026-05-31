"""Distributed coordination: run tracefix agents across nodes.

The whole verified coordination layer (CoordinationContext + stores + Monitor +
StateTracker) is reused UNCHANGED inside a single authoritative
``CoordinationService``. Agents on other processes/machines talk to it through
``CoordClient``, which implements the same ``CoordBackend`` interface as the
in-process ``CoordinationContext`` — so swapping in-process for distributed is
just swapping the object handed to each agent's dispatcher.

Why this preserves the TLA+-verified semantics: the service is one process making
every lock/message/counter decision serially through the existing code. A blocked
``receive``/``acquire_lock`` is simply an HTTP request the service hasn't answered
yet; when another node's ``send``/``release`` fires the server-side
``asyncio.Condition``, the parked coroutine wakes and the long-pending response is
written. The cross-node wake needs no cross-node signalling.
"""

from tracefix.runtime.coordination.backend import CoordBackend
from tracefix.runtime.coordination.client import CoordClient
from tracefix.runtime.coordination.service import CoordinationService

__all__ = ["CoordBackend", "CoordClient", "CoordinationService"]
