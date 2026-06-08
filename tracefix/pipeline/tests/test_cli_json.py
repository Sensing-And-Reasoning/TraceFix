"""CLI machine-readable output / exit-code contract tests (no toolchain needed)."""

from __future__ import annotations

import argparse
import json

from tracefix.cli import cli


def test_verify_json_setup_error_is_valid_json(tmp_path, capsys):
    # Empty dir → no Protocol.tla. With --json this must emit a parseable verdict.
    args = argparse.Namespace(
        dir=str(tmp_path), timeout=10, java_path=None, jar_path=None,
        no_history=True, json=True,
    )
    rc = cli.cmd_verify(args)
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)  # raises if not valid JSON
    assert rc == 1
    assert payload["verdict"] == "error"
    assert "not found" in payload["error"]


def test_verify_human_setup_error_unchanged(tmp_path, capsys):
    args = argparse.Namespace(
        dir=str(tmp_path), timeout=10, java_path=None, jar_path=None,
        no_history=True, json=False,
    )
    rc = cli.cmd_verify(args)
    out = capsys.readouterr().out
    assert rc == 1
    assert out.startswith("ERROR:")
