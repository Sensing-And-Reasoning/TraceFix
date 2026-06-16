"""Tests for the unified `tracefix run` wrapper (no agents are launched)."""

from __future__ import annotations

import argparse
import json

import pytest

from tracefix.runtime import cli


def _make_ws(tmp_path, with_prompts=True, with_ir=True, with_states=False):
    ws = tmp_path / "my_ws"
    (ws / "spec").mkdir(parents=True)
    if with_ir:
        (ws / "spec" / "ir.json").write_text(json.dumps({"agents": [{"id": "A"}]}))
    if with_states:
        (ws / "spec" / "states.json").write_text("{}")
    if with_prompts:
        pd = ws / "prompts" / "runtime_b"
        pd.mkdir(parents=True)
        (pd / "A.md").write_text("# A")
    return ws


def test_derive_task_explicit_wins():
    assert cli._derive_task("/x/foo", "bar") == "bar"


def test_derive_task_from_basename(tmp_path):
    ws = _make_ws(tmp_path)
    assert cli._derive_task(str(ws), None) == "my_ws"


def test_preflight_ok(tmp_path):
    ws = _make_ws(tmp_path)
    assert cli._preflight(str(ws)) == []


def test_preflight_missing_workspace(tmp_path):
    problems = cli._preflight(str(tmp_path / "nope"))
    assert problems and "not found" in problems[0]


def test_preflight_missing_prompts(tmp_path):
    ws = _make_ws(tmp_path, with_prompts=False)
    problems = cli._preflight(str(ws))
    assert any("prompts" in p for p in problems)


def _args(ws, harness="opencode", task=None, model=None, live=False, verbose=False):
    return argparse.Namespace(
        command="run", workspace=str(ws), harness=harness, task=task,
        model=model, live=live, verbose=verbose,
    )


def test_cmd_run_delegates_with_derived_task(tmp_path, monkeypatch):
    ws = _make_ws(tmp_path, with_states=True)
    import tracefix.runtime.opencode_adapter.cli as oc
    captured = {}

    def _fake(argv):
        captured["argv"] = argv
        return 0
    monkeypatch.setattr(oc, "main", _fake)
    # neutralize the opencode-deps preflight (env-dependent; covered separately)
    monkeypatch.setattr(cli, "_opencode_blockers", lambda *a, **k: [])

    rc = cli.cmd_run(_args(ws), ["--opencode-bin", "opencode"])
    assert rc == 0
    assert captured["argv"] == [
        "run", "--task", "my_ws", "--workspace", str(ws), "--opencode-bin", "opencode",
    ]


def test_cmd_run_forwards_common_flags_to_monitoring(tmp_path, monkeypatch):
    ws = _make_ws(tmp_path, with_states=True)
    import tracefix.runtime.monitoring.cli as mon
    captured = {}

    def _fake(argv):
        captured["argv"] = argv
        return 0
    monkeypatch.setattr(mon, "main", _fake)

    rc = cli.cmd_run(_args(ws, harness="monitoring", model="gpt-x", verbose=True),
                     ["--difficulty", "2"])
    assert rc == 0
    argv = captured["argv"]
    assert "--model" in argv and "gpt-x" in argv
    assert "--verbose" in argv
    assert argv[-2:] == ["--difficulty", "2"]


def test_cmd_run_blocks_on_preflight(tmp_path, monkeypatch):
    ws = _make_ws(tmp_path, with_prompts=False)
    import tracefix.runtime.opencode_adapter.cli as oc
    called = {"n": 0}
    monkeypatch.setattr(oc, "main", lambda argv: called.__setitem__("n", called["n"] + 1) or 0)
    rc = cli.cmd_run(_args(ws), [])
    assert rc == 2
    assert called["n"] == 0  # harness never invoked


def test_cmd_run_propagates_systemexit_code(tmp_path, monkeypatch):
    ws = _make_ws(tmp_path, with_states=True)
    import tracefix.runtime.opencode_adapter.cli as oc

    def _boom(argv):
        raise SystemExit(3)
    monkeypatch.setattr(oc, "main", _boom)
    monkeypatch.setattr(cli, "_opencode_blockers", lambda *a, **k: [])
    assert cli.cmd_run(_args(ws), []) == 3


def test_cmd_run_blocks_when_opencode_deps_missing(tmp_path, monkeypatch):
    """The opencode harness refuses to start (and never invokes the harness) when
    its external deps (the opencode CLI / the mcp package) are absent."""
    ws = _make_ws(tmp_path, with_states=True)
    import tracefix.runtime.opencode_adapter.cli as oc
    called = {"n": 0}
    monkeypatch.setattr(oc, "main", lambda argv: called.__setitem__("n", called["n"] + 1) or 0)
    monkeypatch.setattr(cli, "_opencode_blockers", lambda *a, **k: ["opencode CLI not found"])
    rc = cli.cmd_run(_args(ws), [])
    assert rc == 2
    assert called["n"] == 0  # harness never invoked


def test_cmd_run_monitoring_harness_skips_opencode_check(tmp_path, monkeypatch):
    """A non-opencode harness must not be gated by the opencode-deps preflight."""
    ws = _make_ws(tmp_path, with_states=True)
    import tracefix.runtime.monitoring.cli as mon
    monkeypatch.setattr(mon, "main", lambda argv: 0)
    # would raise if consulted for a non-opencode harness
    def _explode(*a, **k):
        raise AssertionError("opencode preflight ran for a non-opencode harness")
    monkeypatch.setattr(cli, "_opencode_blockers", _explode)
    assert cli.cmd_run(_args(ws, harness="monitoring"), []) == 0


def test_opencode_bin_from_passthrough():
    assert cli._opencode_bin_from([]) == "opencode"
    assert cli._opencode_bin_from(["--model", "x", "--opencode-bin", "foo"]) == "foo"
    assert cli._opencode_bin_from(["--opencode-bin=/usr/bin/oc"]) == "/usr/bin/oc"
