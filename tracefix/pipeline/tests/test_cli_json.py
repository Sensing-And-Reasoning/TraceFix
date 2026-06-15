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


# --- guide: single-source design knowledge for the TUI designer -------------

def test_guide_default_inlines_workflow_and_references(capsys):
    """No-arg guide → SKILL workflow + all three references, in one shot."""
    import sys as _sys
    args = argparse.Namespace(section=None)
    rc = cli.cmd_guide(args)
    out = capsys.readouterr().out
    assert rc == 0
    # workflow body (frontmatter stripped — no leading YAML)
    assert not out.lstrip().startswith("---")
    # the three references are inlined under their markers
    assert out.count("===== reference:") == 3
    # patch-14 disciplines reach the TUI via the guide (not a private copy)
    assert "Write rule (disambiguates Lock vs Counter)" in out
    assert "only relays messages" in out


def test_guide_sections_resolve(capsys):
    for section in ("pluscal", "schema", "plan", "prompts"):
        rc = cli.cmd_guide(argparse.Namespace(section=section))
        out = capsys.readouterr().out
        assert rc == 0 and out.strip(), f"guide {section} produced nothing"


def test_guide_resolves_skill_root_from_package():
    # Must resolve from the installed package, not cwd, so the TUI finds it
    # wherever it runs.
    root = cli._find_skill_root()
    assert root is not None
    assert (root / cli._SKILL_DESIGN / "SKILL.md").exists()
