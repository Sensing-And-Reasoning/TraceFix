"""Validator tests — focused on the optional data-plane `content_labels` annotation."""

import copy

from tracefix.pipeline.pipeline.validator import validate_ir

BASE = {
    "agents": [{"id": "A"}, {"id": "B"}],
    "resources": [],
    "channels": [{"id": "a_to_b", "from": "A", "to": "B", "labels": ["accept", "revise"]}],
}


def _with_channel(**over):
    ir = copy.deepcopy(BASE)
    ir["channels"][0].update(over)
    return ir


def test_no_content_labels_is_valid():
    r = validate_ir(copy.deepcopy(BASE))
    assert r.valid, r.errors


def test_content_labels_subset_is_valid():
    r = validate_ir(_with_channel(content_labels=["revise"]))
    assert r.valid, r.errors


def test_content_labels_not_a_subset_is_rejected():
    r = validate_ir(_with_channel(content_labels=["bogus", "revise"]))
    assert not r.valid
    assert any("content_labels" in e and "bogus" in e for e in r.errors)
