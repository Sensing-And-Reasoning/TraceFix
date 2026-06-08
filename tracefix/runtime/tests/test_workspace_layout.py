"""Tests for the per-run snapshot workspace helpers (timestamped, traceable runs)."""

from __future__ import annotations

import re
from pathlib import Path

from tracefix.runtime.workspace_layout import (
    agent_workdir,
    new_run_stamp,
    shared_workdir,
    snapshot_run_workspace,
)


def _make_base(root: Path) -> Path:
    """A minimal base workspace: inputs + verified spec/ + prompts/ + a stale output/."""
    base = root / "mas_research"
    (base / "spec").mkdir(parents=True)
    (base / "spec" / "ir.json").write_text('{"agents": []}')
    (base / "spec" / "states.json").write_text("{}")
    (base / "prompts" / "runtime_b").mkdir(parents=True)
    (base / "prompts" / "runtime_b" / "A.md").write_text("prompt A")
    (base / "tools.json").write_text("[]")
    (base / "output").mkdir()  # a prior run's output — must NOT be copied
    (base / "output" / "stale.md").write_text("old")
    return base


def test_new_run_stamp_is_sortable():
    # YYYYmmdd-HHMMSS → lexicographic order == chronological order.
    assert re.fullmatch(r"\d{8}-\d{6}", new_run_stamp())


def test_snapshot_is_sibling_named_by_stamp(tmp_path: Path):
    base = _make_base(tmp_path)
    snap = snapshot_run_workspace(base, "20260101-000000")
    assert snap == tmp_path / "mas_research-20260101-000000"
    assert snap.is_dir()


def test_snapshot_copies_spec_and_prompts_with_fresh_output(tmp_path: Path):
    base = _make_base(tmp_path)
    snap = snapshot_run_workspace(base, "20260101-000000")
    # full pipeline source is carried in
    assert (snap / "spec" / "ir.json").read_text() == '{"agents": []}'
    assert (snap / "spec" / "states.json").exists()
    assert (snap / "prompts" / "runtime_b" / "A.md").read_text() == "prompt A"
    assert (snap / "tools.json").exists()
    # output/ is fresh and empty — the base's prior output is NOT carried in
    assert (snap / "output").is_dir()
    assert not (snap / "output" / "stale.md").exists()


def test_successive_snapshots_do_not_overwrite(tmp_path: Path):
    base = _make_base(tmp_path)
    a = snapshot_run_workspace(base, "20260101-000000")
    (a / "output" / "research.md").write_text("run A")
    b = snapshot_run_workspace(base, "20260101-000001")
    (b / "output" / "research.md").write_text("run B")
    assert a != b
    assert (a / "output" / "research.md").read_text() == "run A"
    assert (b / "output" / "research.md").read_text() == "run B"


def test_latest_symlink_points_at_newest(tmp_path: Path):
    base = _make_base(tmp_path)
    a = snapshot_run_workspace(base, "20260101-000000")
    latest = tmp_path / "mas_research-latest"
    if not latest.is_symlink():
        return  # filesystem without symlink support — timestamped dir is canonical
    assert latest.resolve() == a.resolve()
    b = snapshot_run_workspace(base, "20260101-000001")
    assert latest.resolve() == b.resolve()  # repointed to the newest run


# --- per-agent private dir + shared area convention ---

def test_shared_workdir_creates_shared(tmp_path: Path):
    out = tmp_path / "output"; out.mkdir()
    d = shared_workdir(out)
    assert d == out / "shared" and d.is_dir()


def test_agent_workdir_is_private_and_sanitized(tmp_path: Path):
    out = tmp_path / "output"; out.mkdir()
    a = agent_workdir(out, "RESEARCHER_FM")
    assert a == out / "RESEARCHER_FM" and a.is_dir()
    b = agent_workdir(out, "agent/../x y")  # weird chars sanitized to a safe name
    assert b.is_dir() and b.parent == out and "/" not in b.name and " " not in b.name


def test_agent_named_shared_never_collides(tmp_path: Path):
    out = tmp_path / "output"; out.mkdir()
    assert agent_workdir(out, "shared") != shared_workdir(out)


def test_private_and_shared_are_siblings(tmp_path: Path):
    out = tmp_path / "output"; out.mkdir()
    shared, priv = shared_workdir(out), agent_workdir(out, "A")
    assert shared.parent == priv.parent == out and shared != priv
