"""Tests for the ConversationStore — the data-plane business-content store."""

from tracefix.runtime.store import ConversationStore


def test_put_returns_opaque_ref_and_get_resolves():
    cs = ConversationStore()
    e = cs.put("REVIEWER", "tighten the abstract; cite X in §2", content_type="review")
    assert e.ref and e.ref.startswith("cs_")
    assert e.sender == "REVIEWER" and e.content_type == "review"
    got = cs.get(e.ref)
    assert got is not None and got.content == "tighten the abstract; cite X in §2"


def test_refs_are_unique_and_membership_works():
    cs = ConversationStore()
    r1 = cs.put("A", "one").ref
    r2 = cs.put("A", "two").ref
    assert r1 != r2
    assert r1 in cs and r2 in cs
    assert "cs_does_not_exist" not in cs
    assert cs.get("cs_does_not_exist") is None


def test_entries_are_append_only():
    cs = ConversationStore()
    r = cs.put("A", "original").ref
    cs.put("A", "another")
    # the original entry is never overwritten (append-only)
    assert cs.get(r).content == "original"
