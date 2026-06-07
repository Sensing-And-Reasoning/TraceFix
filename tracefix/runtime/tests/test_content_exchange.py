"""Gated business-content exchange (the reviewer→writer demo at the dispatcher level).

Content flows only on content-carrying labels (revise), never on pure signals
(accept). Content rides the ConversationStore via an opaque ref; the channel carries
only the label (+ the gated ref). The control plane never sees the content.
"""

import asyncio

from tracefix.runtime.monitoring.coord import CoordinationContext
from tracefix.runtime.monitoring.monitor import ProtocolMonitor
from tracefix.runtime.sdk_adapter.dispatch import CoordToolDispatcher, COORD_TOOL_NAMES

IR = {
    "agents": [{"id": "REVIEWER"}, {"id": "WRITER"}],
    "resources": [],
    "channels": [
        {"id": "reviewer_to_writer", "from": "REVIEWER", "to": "WRITER",
         "labels": ["accept", "revise"], "content_labels": ["revise"]},
    ],
}


def _coord():
    return CoordinationContext(IR, ProtocolMonitor(IR))


def test_revise_carries_content_via_ref():
    async def scenario():
        coord = _coord()
        rev = CoordToolDispatcher(coord, "REVIEWER")
        wri = CoordToolDispatcher(coord, "WRITER")
        # REVIEWER stores suggestions on the data plane → opaque ref.
        p = await rev.dispatch("post_content",
                               {"content": "tighten the abstract; cite X in §2",
                                "content_type": "review"})
        assert p["status"] == "ok" and p["ref"]
        # 'revise' is content-carrying: send carries only the ref (no prose on channel).
        s = await rev.dispatch("send_message", {
            "channel_id": "reviewer_to_writer", "label": "revise", "ref": p["ref"]})
        assert s["status"] == "sent" and s["ref"] == p["ref"]
        # WRITER receives the label + ref, then resolves the content.
        r = await wri.dispatch("receive_message", {"channel_id": "reviewer_to_writer"})
        assert r["label"] == "revise" and r["ref"] == p["ref"]
        g = await wri.dispatch("get_content", {"ref": r["ref"]})
        assert g["status"] == "ok" and "tighten the abstract" in g["content"]
        assert g["sender"] == "REVIEWER" and g["content_type"] == "review"

    asyncio.run(scenario())


def test_accept_is_pure_signal_no_content_channel():
    async def scenario():
        coord = _coord()
        rev = CoordToolDispatcher(coord, "REVIEWER")
        wri = CoordToolDispatcher(coord, "WRITER")
        s = await rev.dispatch("send_message",
                               {"channel_id": "reviewer_to_writer", "label": "accept"})
        assert s["status"] == "sent" and "ref" not in s
        r = await wri.dispatch("receive_message", {"channel_id": "reviewer_to_writer"})
        assert r["label"] == "accept" and "ref" not in r  # content channel stayed closed

    asyncio.run(scenario())


def test_ref_on_pure_signal_label_is_rejected():
    async def scenario():
        coord = _coord()
        rev = CoordToolDispatcher(coord, "REVIEWER")
        ref = (await rev.dispatch("post_content", {"content": "x"}))["ref"]
        s = await rev.dispatch("send_message", {
            "channel_id": "reviewer_to_writer", "label": "accept", "ref": ref})
        assert s["status"] == "error" and "pure signal" in s["message"]

    asyncio.run(scenario())


def test_content_label_requires_a_ref():
    async def scenario():
        coord = _coord()
        rev = CoordToolDispatcher(coord, "REVIEWER")
        s = await rev.dispatch("send_message",
                               {"channel_id": "reviewer_to_writer", "label": "revise"})
        assert s["status"] == "error" and "carries content" in s["message"]

    asyncio.run(scenario())


def test_unknown_ref_is_rejected():
    async def scenario():
        coord = _coord()
        rev = CoordToolDispatcher(coord, "REVIEWER")
        s = await rev.dispatch("send_message", {
            "channel_id": "reviewer_to_writer", "label": "revise", "ref": "cs_999"})
        assert s["status"] == "error" and "unknown content ref" in s["message"]

    asyncio.run(scenario())


def test_content_tools_bypass_the_control_plane():
    # Data-plane tools must NOT be coordination ops (never validated by the monitor).
    assert "post_content" not in COORD_TOOL_NAMES
    assert "get_content" not in COORD_TOOL_NAMES
