"""Mechanical checks for the underspecified (narrative) benchmark tier.

These guard the tier's two contracts WITHOUT any LLM call:
  - every narrative is genuinely unscaffolded (no headings enumerating
    agents/resources, no canonical IDs leaked from the parent task), and
  - every tier task wires back to a real parent with a non-empty checklist
    (the scoring ground truth).
"""

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
TIER = REPO / "benchmark" / "underspecified"

TASKS = sorted(p.name for p in TIER.iterdir()
               if p.is_dir() and (p / "description.md").exists()) if TIER.exists() else []


def test_tier_exists_and_nonempty():
    assert TASKS, "benchmark/underspecified/ has no tasks"


@pytest.mark.parametrize("task_id", TASKS)
class TestTierTask:
    def _meta(self, task_id):
        return json.loads((TIER / task_id / "meta.json").read_text())

    def _narrative(self, task_id):
        return (TIER / task_id / "description.md").read_text()

    def test_parent_resolves(self, task_id):
        meta = self._meta(task_id)
        parent = meta["parent"]
        assert (REPO / "benchmark" / "descriptions" / parent / "description.md").exists()
        checklist = json.loads(
            (REPO / "benchmark" / "environments" / parent / "checklist.json").read_text())
        assert checklist, f"{parent} checklist is empty"

    def test_no_scaffolding_headings(self, task_id):
        text = self._narrative(task_id)
        assert not re.search(r"^#{1,6}\s", text, re.M), \
            "narrative must be plain prose (no markdown headings)"
        assert not re.search(r"^\s*[-*]\s", text, re.M), \
            "narrative must not enumerate via bullet lists"

    def test_no_canonical_ids_leaked(self, task_id):
        meta = self._meta(task_id)
        parent_meta = json.loads(
            (REPO / "benchmark" / "descriptions" / meta["parent"] / "metadata.json").read_text())
        text = self._narrative(task_id)
        leaked = [cid for cid in parent_meta["agents"] + parent_meta["resources"]
                  if re.search(rf"\b{re.escape(cid)}\b", text)]
        assert not leaked, f"canonical IDs leaked into narrative: {leaked}"

    def test_no_formal_vocabulary(self, task_id):
        text = self._narrative(task_id)
        hits = [w for w in ("Lock", "Counter", "channel", "mutex", "FIFO")
                if re.search(rf"\b{w}\b", text)]
        assert not hits, f"IR vocabulary leaked into narrative: {hits}"

    def test_narrative_is_substantial(self, task_id):
        words = len(self._narrative(task_id).split())
        assert 60 <= words <= 260, f"narrative is {words} words (want prose, not a stub or a spec)"


def test_eval_loader_roundtrip():
    from benchmark.underspec_eval import load_narrative, tier_tasks
    assert tier_tasks() == TASKS
    for t in TASKS:
        loaded = load_narrative(t)
        assert loaded["narrative"] and loaded["checklist"]
        assert loaded["parent"] == json.loads((TIER / t / "meta.json").read_text())["parent"]
