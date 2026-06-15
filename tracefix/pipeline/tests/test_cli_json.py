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


# --- extract-states: generate domain tools.json + impl scaffolds ------------

def test_generate_domain_tools_writes_schema_and_stubs(tmp_path, capsys):
    spec = tmp_path / "spec"
    spec.mkdir()
    tla = (
        "BILLING_charge:\n  skip; \\* domain: charge card "
        "[tool: charge_payment(amount: number) -> {ok}; impl: external]\n"
        "AUDIT_log:\n  skip; \\* domain: write audit row "
        "[tool: audit(msg: string); impl: local]\n"
    )
    states = [{"id": "BILLING_charge", "agent": "BILLING"},
              {"id": "AUDIT_log", "agent": "AUDIT"}]
    cli._generate_domain_tools(spec, tla, states)

    # tools.json at the WORKSPACE ROOT (spec's parent), per-agent assigned
    tools = json.loads((tmp_path / "tools.json").read_text())
    by = {t["function"]["name"]: t["function"] for t in tools}
    assert by["charge_payment"]["agent_ids"] == ["BILLING"]
    assert by["audit"]["agent_ids"] == ["AUDIT"]
    # local impl → python stub; external → mcp.json stub
    impl = (tmp_path / "tools_impl.py").read_text()
    assert "def audit(msg):" in impl and "NotImplementedError" in impl
    assert "charge_payment" not in impl  # external, not a local impl
    mcp = json.loads((tmp_path / "mcp.json").read_text())
    assert "charge_payment_service" in mcp["mcpServers"]
    assert mcp["mcpServers"]["charge_payment_service"]["agent_ids"] == ["BILLING"]


def test_generate_domain_tools_noop_without_tags(tmp_path):
    spec = tmp_path / "spec"
    spec.mkdir()
    tla = "PICKER_pick:\n  skip; \\* domain: gather items from storage\n"
    cli._generate_domain_tools(spec, tla, [{"id": "PICKER_pick", "agent": "PICKER"}])
    assert not (tmp_path / "tools.json").exists()  # builtins-only → nothing generated


def test_generate_domain_tools_preserves_filled_impl(tmp_path):
    spec = tmp_path / "spec"
    spec.mkdir()
    (tmp_path / "tools_impl.py").write_text("def audit(msg):\n    return {'logged': True}\n")
    tla = "A_log:\n  skip; \\* domain: log [tool: audit(msg: string); impl: local]\n"
    cli._generate_domain_tools(spec, tla, [{"id": "A_log", "agent": "A"}])
    # user's filled impl is NOT clobbered
    assert "return {'logged': True}" in (tmp_path / "tools_impl.py").read_text()
