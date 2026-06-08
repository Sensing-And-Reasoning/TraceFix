"""tla-verify-pluscal CLI — PlusCal-based TLA+ verification.

Usage:
    tla-verify-pluscal validate ir.json
    tla-verify-pluscal scaffold ir.json [-o dir]
    tla-verify-pluscal verify [dir] [--timeout 120]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


def _resolve_java(args: argparse.Namespace) -> str:
    from tracefix.pipeline.pipeline.toolchain import resolve_java

    return resolve_java(getattr(args, "java_path", None))


def _resolve_jar(args: argparse.Namespace) -> str:
    from tracefix.pipeline.pipeline.toolchain import resolve_jar

    return resolve_jar(getattr(args, "jar_path", None))


def _load_ir(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _output_dir(args: argparse.Namespace, ir_path: str) -> Path:
    if hasattr(args, "output") and args.output:
        d = Path(args.output)
    else:
        d = Path(ir_path).parent
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def cmd_validate(args: argparse.Namespace) -> int:
    from tracefix.pipeline.pipeline.validator import validate_ir

    ir_data = _load_ir(args.ir_json)
    result = validate_ir(ir_data)

    if result.valid:
        print("VALID")
        return 0
    else:
        print("INVALID")
        for err in result.errors:
            print(f"  - {err}")
        return 1


# ---------------------------------------------------------------------------
# scaffold
# ---------------------------------------------------------------------------

def cmd_scaffold(args: argparse.Namespace) -> int:
    from tracefix.pipeline.pipeline.validator import validate_ir
    from tracefix.pipeline.pipeline.pluscal_generator import (
        generate_pluscal_scaffold,
        generate_tlc_config,
    )

    ir_data = _load_ir(args.ir_json)

    vr = validate_ir(ir_data)
    if not vr.valid:
        print("INVALID IR — cannot generate scaffold")
        for err in vr.errors:
            print(f"  - {err}")
        return 1

    tla_spec = generate_pluscal_scaffold(ir_data, channel_bound=args.channel_bound, depth_bound=args.depth_bound)
    tlc_cfg = generate_tlc_config(ir_data, channel_bound=args.channel_bound, depth_bound=args.depth_bound)

    out = _output_dir(args, args.ir_json)
    tla_path = out / "Protocol.tla"
    cfg_path = out / "Protocol.cfg"

    tla_path.write_text(tla_spec)
    cfg_path.write_text(tlc_cfg)

    print(f"OK — wrote {tla_path} and {cfg_path}")
    print("Next: fill in PlusCal process bodies in Protocol.tla, then run: tla-verify-pluscal verify")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Scaffold a custom-task workspace: description.md + ir.json stub (+ tools.json)."""
    out = Path(args.dir)
    # Bare name (no path separator) → default under the gitignored workspace/ root,
    # keeping generated artifacts out of the repo. An explicit path is used as-is.
    if out.parent == Path("."):
        out = Path("workspace") / out
    out.mkdir(parents=True, exist_ok=True)
    agents = [a.strip() for a in (args.agents or "").split(",") if a.strip()]

    desc_path = out / "description.md"
    if not desc_path.exists():
        desc = args.task or (
            "# <task title>\n\n"
            "Describe the multi-agent coordination scenario in prose: the concurrent agents,\n"
            "the shared resources they contend over, the ordering constraints between them, and\n"
            "what happens on failure. TraceFix derives the protocol from this.\n")
        desc_path.write_text(desc if desc.endswith("\n") else desc + "\n")

    # Spec artifacts (ir.json now, Protocol.tla/states.json later) live in spec/.
    ir_path = out / "spec" / "ir.json"
    if not ir_path.exists():
        ir_path.parent.mkdir(parents=True, exist_ok=True)
        ir = {
            "agents": [{"id": a} for a in agents] or [{"id": "AGENT_A"}, {"id": "AGENT_B"}],
            "resources": [],
            "channels": [],
        }
        ir_path.write_text(json.dumps(ir, indent=2) + "\n")

    if args.with_tools:
        tools_path = out / "tools.json"
        if not tools_path.exists():
            template = [{
                "type": "function",
                "function": {
                    "name": "do_work",
                    "description": "Replace with a real domain tool (or delete this file to "
                                   "use the runtime's SDK builtins as the domain layer).",
                    "agent_ids": agents,
                    "can_fail": False,
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }]
            tools_path.write_text(json.dumps(template, indent=2) + "\n")

    print(f"OK — initialized custom workspace at {out}")
    print("  - description.md  (input: describe your scenario)")
    print("  - spec/ir.json    (edit: fill resources + channels"
          f"{'' if agents else ' + agent ids'})")
    if args.with_tools:
        print("  - tools.json      (input: domain tools, or delete to use SDK builtins)")
    print("  layout: spec/ (verification artifacts) · prompts/ (per-agent prompts) "
          "· output/ (runtime artifacts)")
    print(f"Next: edit {out}/spec/ir.json, then run: tla-verify-pluscal scaffold {out}/spec/ir.json")
    return 0


# ---------------------------------------------------------------------------
# attempt history helper
# ---------------------------------------------------------------------------

def _save_attempt_history(search_dir: Path) -> Path | None:
    """Archive the current Protocol.tla + error files into history/attempt_{N}/.

    Returns the created directory, or None if Protocol.tla doesn't exist.
    """
    tla_src = search_dir / "Protocol.tla"
    if not tla_src.exists():
        return None

    history_dir = search_dir / "history"
    # Determine next attempt number
    existing = sorted(history_dir.glob("attempt_*")) if history_dir.exists() else []
    nums = []
    for d in existing:
        try:
            nums.append(int(d.name.split("_", 1)[1]))
        except (ValueError, IndexError):
            pass
    next_num = (max(nums) + 1) if nums else 1

    attempt_dir = history_dir / f"attempt_{next_num}"
    attempt_dir.mkdir(parents=True, exist_ok=True)

    # Copy Protocol.tla and optional error artifacts
    shutil.copy2(tla_src, attempt_dir / "Protocol.tla")
    for fname in ("tlc_error.md", "tlc_output.log"):
        src = search_dir / fname
        if src.exists():
            shutil.copy2(src, attempt_dir / fname)

    return attempt_dir


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def cmd_verify(args: argparse.Namespace) -> int:
    from tracefix.pipeline.pipeline.validator import validate_ir
    from tracefix.pipeline.pipeline.pluscal_compiler import translate_pluscal
    from tracefix.pipeline.pipeline.tlc_runner import run_tlc
    from tracefix.pipeline.pipeline.trace_parser import parse_trace
    from tracefix.pipeline.pipeline.error_formatter import format_tlc_error

    as_json = getattr(args, "json", False)
    search_dir = Path(args.dir)
    tla_path = search_dir / "Protocol.tla"
    cfg_path = search_dir / "Protocol.cfg"
    ir_path = search_dir / "ir.json"

    def _setup_error(msg: str, extra: dict | None = None) -> int:
        if as_json:
            print(json.dumps({"verdict": "error", "error": msg, **(extra or {})}))
        else:
            print(f"ERROR: {msg}")
            for e in (extra or {}).get("ir_errors", []):
                print(f"  - {e}")
        return 1

    if not tla_path.exists():
        return _setup_error(f"{tla_path} not found")
    if not cfg_path.exists():
        return _setup_error(f"{cfg_path} not found")

    # Step 1: Validate IR if present
    if ir_path.exists():
        ir_data = _load_ir(str(ir_path))
        vr = validate_ir(ir_data)
        if not vr.valid:
            return _setup_error("invalid IR", {"ir_errors": vr.errors})

    tla_content = tla_path.read_text()
    cfg_content = cfg_path.read_text()

    # Step 2: Translate PlusCal → TLA+
    pcal_result = translate_pluscal(
        tla_content,
        cfg_content,
        java_path=_resolve_java(args),
        tla2tools_jar=_resolve_jar(args),
    )

    if not pcal_result.success:
        error_path = search_dir / "tlc_error.md"
        error_path.write_text(f"# PlusCal Translation Error\n\n{pcal_result.error_message}")
        archived = (None if getattr(args, "no_history", False)
                    else _save_attempt_history(search_dir))
        if as_json:
            print(json.dumps({
                "verdict": "fail", "violation_type": "pcal_error",
                "error": pcal_result.error_message,
                "files": {"error": str(error_path)},
                "archived": str(archived) if archived else None,
            }))
        else:
            print("FAIL — PlusCal syntax error:")
            print(pcal_result.error_message)
            print(f"\nSaved: {error_path}")
            if archived:
                print(f"Archived: {archived}")
        return 1

    # Save translated TLA+ (PlusCal source + generated TLA+ translation block)
    translated_path = search_dir / "Protocol_translated.tla"
    translated_path.write_text(pcal_result.translated_tla)

    # Step 3: Run TLC on translated spec
    tlc_result = run_tlc(
        pcal_result.translated_tla,
        cfg_content,
        timeout=args.timeout,
        java_path=_resolve_java(args),
        tla2tools_jar=_resolve_jar(args),
    )

    # Save raw output
    log_path = search_dir / "tlc_output.log"
    log_path.write_text(tlc_result.raw_output)

    if tlc_result.success:
        stats = tlc_result.stats or {}
        if as_json:
            print(json.dumps({
                "verdict": "pass", "violation_type": None,
                "states_generated": stats.get("states_generated"),
                "distinct_states": stats.get("distinct_states"),
                "elapsed_seconds": stats.get("elapsed_seconds"),
                "files": {"translated": str(translated_path), "log": str(log_path)},
            }))
        else:
            print("PASS")
            parts = []
            if "states_generated" in stats:
                parts.append(f"states={stats['states_generated']}")
            if "distinct_states" in stats:
                parts.append(f"distinct={stats['distinct_states']}")
            if "elapsed_seconds" in stats:
                parts.append(f"time={stats['elapsed_seconds']:.1f}s")
            if parts:
                print(f"  {', '.join(parts)}")
            print(f"\nSaved: {translated_path}, {log_path}")
        return 0
    else:
        trace = parse_trace(tlc_result.raw_output)
        error_md = format_tlc_error(tlc_result, trace)
        error_path = search_dir / "tlc_error.md"
        error_path.write_text(error_md)
        archived = (None if getattr(args, "no_history", False)
                    else _save_attempt_history(search_dir))
        if as_json:
            print(json.dumps({
                "verdict": "fail",
                "violation_type": tlc_result.violation_type,
                "error_trace": tlc_result.error_trace,
                "files": {"translated": str(translated_path), "log": str(log_path),
                          "error": str(error_path)},
                "archived": str(archived) if archived else None,
            }))
        else:
            print(f"FAIL — {tlc_result.violation_type or 'unknown error'}")
            print(error_md)
            print(f"\nSaved: {translated_path}, {log_path}, {error_path}")
            if archived:
                print(f"Archived: {archived}")
        return 1


# ---------------------------------------------------------------------------
# extract-states
# ---------------------------------------------------------------------------

def _annotate_tool_hints(states: list[dict]) -> None:
    """Add tool_hint to multi-action states for prompt generation."""
    for state in states:
        actions = state.get("actions", [])
        if len(actions) <= 1:
            continue
        has_recv = [bool(a.get("receive")) for a in actions]
        if all(has_recv):
            state["tool_hint"] = "receive_any"
        elif any(has_recv):
            state["tool_hint"] = "poll_channels"
        # else: pure nondeterminism — no hint needed (LLM judgment)


def cmd_extract_states(args: argparse.Namespace) -> int:
    search_dir = Path(args.dir)
    tla_path = search_dir / "Protocol_translated.tla"
    ir_path = search_dir / "ir.json"

    if not tla_path.exists():
        print(f"ERROR: {tla_path} not found")
        return 1
    if not ir_path.exists():
        print(f"ERROR: {ir_path} not found")
        return 1

    ir_data = _load_ir(str(ir_path))
    tla_content = tla_path.read_text()

    if getattr(args, "legacy", False):
        from tracefix.pipeline.pipeline.tla_parser import parse_translated_tla
        result = parse_translated_tla(tla_content, ir_data)
    else:
        from tracefix.pipeline.pipeline.pluscal_parser import parse_pluscal
        result = parse_pluscal(tla_content, ir_data)

    if result.errors:
        print(f"WARNING: {len(result.errors)} parse error(s):")
        for err in result.errors:
            print(f"  - {err}")

    # Annotate multi-action states with tool_hint for prompt generation
    _annotate_tool_hints(result.states)

    # Per-state BUSINESS-task annotation (observability only; ignored by TLC).
    # Default each task from the `\* domain:` PlusCal comment the design flow already
    # writes; the IR's optional `state_tasks` map then overrides. Orphan keys warn.
    from tracefix.pipeline.pipeline.pluscal_parser import (
        inject_state_tasks, lift_domain_tasks)
    lift_domain_tasks(result.states, tla_content)
    task_orphans = inject_state_tasks(result.states, ir_data.get("state_tasks", {}))
    if task_orphans:
        print(f"WARNING: {len(task_orphans)} state_tasks key(s) match no state "
              f"(typo, or stale after a repair?): {', '.join(sorted(task_orphans))}")

    # Lint: check for adjacent acquire→release without intermediate work
    from tracefix.pipeline.pipeline.pluscal_parser import lint_adjacent_acquire_release
    lint_warnings = lint_adjacent_acquire_release(result.states)
    if lint_warnings:
        print(f"LINT: {len(lint_warnings)} work-state warning(s):")
        for w in lint_warnings:
            print(f"  \u26a0 {w}")

    if args.merge:
        ir_data["states"] = result.states
        ir_path.write_text(json.dumps(ir_data, indent=2) + "\n")
        print(f"OK — merged {len(result.states)} states into {ir_path}")
    else:
        out_path = search_dir / "states.json"
        out_data = {
            "states": result.states,
            "initial_states": result.initial_states,
        }
        if result.local_variables:
            out_data["local_variables"] = result.local_variables
        out_path.write_text(json.dumps(out_data, indent=2) + "\n")
        print(f"OK — wrote {len(result.states)} states to {out_path}")

    n_actions = sum(len(s.get("actions", [])) for s in result.states)
    n_terminal = sum(1 for s in result.states if not s.get("actions"))
    print(f"  {len(result.states)} states, {n_actions} actions, {n_terminal} terminal")

    # Exit-code semantics for CI: parse errors are FATAL (states.json may be
    # incomplete → the runtime would consume a broken state machine). Cosmetic
    # warnings (orphan state_tasks keys, lint) are non-fatal unless --strict.
    n_warnings = len(task_orphans) + len(lint_warnings)
    if result.errors:
        print(f"FATAL: {len(result.errors)} parse error(s) — states.json may be "
              f"incomplete; do not run this protocol until they are fixed.")
        return 1
    if getattr(args, "strict", False) and n_warnings:
        print(f"STRICT: failing on {n_warnings} warning(s) (orphan state_tasks / lint).")
        return 1
    return 0


# ---------------------------------------------------------------------------
# doctor — verify the toolchain (Java 17 + tla2tools.jar + tree-sitter)
# ---------------------------------------------------------------------------

def _examples_dir() -> Path:
    root = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
    return root / "examples" / "2pc_minimal"


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check the verification toolchain and (optionally) smoke-test a bundled spec.

    No LLM and no API keys required. Exit 0 if every component is usable.
    """
    from tracefix.pipeline.pipeline.toolchain import (
        JAR_MISSING_HINT,
        JAVA_MISSING_HINT,
        java_major_version,
        resolve_jar,
        resolve_java,
    )

    print("TraceFix toolchain check\n")
    ok = True

    # 1. Java
    java = _resolve_java(args)
    ver = java_major_version(java)
    if ver is None:
        print(f"  [FAIL] Java        not runnable at {java}")
        print(f"         {JAVA_MISSING_HINT}")
        ok = False
    elif ver != "17":
        print(f"  [WARN] Java        found v{ver} at {java} (TraceFix is tested on Java 17)")
    else:
        print(f"  [ OK ] Java 17     {java}")

    # 2. tla2tools.jar
    jar = _resolve_jar(args)
    if not Path(jar).exists():
        print(f"  [FAIL] tla2tools   not found at {jar}")
        print(f"         {JAR_MISSING_HINT}")
        ok = False
    else:
        print(f"  [ OK ] tla2tools   {jar}")

    # 3. tree-sitter (needed by extract-states)
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_tlaplus  # noqa: F401
        print("  [ OK ] tree-sitter tree-sitter + tree-sitter-tlaplus importable")
    except Exception as e:  # pragma: no cover - import-environment dependent
        print(f"  [FAIL] tree-sitter not importable: {e}")
        print("         Run: pip install -e .")
        ok = False

    # 4. Optional end-to-end smoke test on the bundled, verified 2PC example
    example = _examples_dir()
    if getattr(args, "no_smoke", False):
        pass
    elif not ok:
        print("\n  [skip] smoke test skipped (fix the failures above first)")
    elif not (example / "Protocol.tla").exists():
        print(f"\n  [skip] smoke test skipped (no bundled example at {example})")
    else:
        from tracefix.pipeline.pipeline.pluscal_compiler import translate_pluscal
        from tracefix.pipeline.pipeline.tlc_runner import run_tlc

        tla = (example / "Protocol.tla").read_text()
        cfg = (example / "Protocol.cfg").read_text()
        pcal = translate_pluscal(tla, cfg, java_path=java, tla2tools_jar=jar)
        if not pcal.success:
            print(f"\n  [FAIL] smoke test  PlusCal translation failed: {pcal.error_message[:200]}")
            ok = False
        else:
            res = run_tlc(pcal.translated_tla, cfg, timeout=120, java_path=java, tla2tools_jar=jar)
            if res.success:
                distinct = res.stats.get("distinct_states", "?")
                print(f"\n  [ OK ] smoke test  verified examples/2pc_minimal "
                      f"({distinct} distinct states)")
            else:
                print(f"\n  [FAIL] smoke test  TLC verdict: {res.violation_type}")
                ok = False

    print("\n" + ("All checks passed — you're ready to verify protocols."
                  if ok else "Some checks FAILED — see the hints above."))
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="tla-verify-pluscal",
        description="PlusCal-based TLA+ verification of multi-agent coordination protocols",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # doctor
    p_doc = sub.add_parser("doctor", help="Check the toolchain (Java 17 + tla2tools.jar + tree-sitter)")
    p_doc.add_argument("--java-path", help="Path to Java 17 binary")
    p_doc.add_argument("--jar-path", help="Path to tla2tools.jar")
    p_doc.add_argument("--no-smoke", action="store_true",
                       help="Skip the end-to-end smoke test on the bundled example")

    # init
    p_ini = sub.add_parser("init", help="Scaffold a custom-task workspace (description + ir stub)")
    p_ini.add_argument("dir", help="Workspace name (a bare name is created under "
                                   "workspace/; an explicit path is used as-is)")
    p_ini.add_argument("--task", help="Task description text (else a template is written)")
    p_ini.add_argument("--agents", help="Comma-separated agent IDs (e.g. ONCALL,DBA,RELEASER)")
    p_ini.add_argument("--with-tools", action="store_true",
                       help="Also write a tools.json template (omit to use SDK builtins)")

    # validate
    p_val = sub.add_parser("validate", help="Validate IR (agents/resources/channels)")
    p_val.add_argument("ir_json", help="Path to IR JSON file")

    # scaffold
    p_scf = sub.add_parser("scaffold", help="Validate + generate PlusCal scaffold")
    p_scf.add_argument("ir_json", help="Path to IR JSON file")
    p_scf.add_argument("-o", "--output", help="Output directory (default: same as ir.json)")
    p_scf.add_argument("--channel-bound", type=int, default=3, help="Max channel queue depth for ChannelBound CONSTRAINT (default: 3, 0 to disable)")
    p_scf.add_argument("--depth-bound", type=int, default=0, help="Max BFS depth for DepthBound CONSTRAINT via TLCGet (default: 0 = disabled)")

    # verify
    p_ver = sub.add_parser("verify", help="Translate PlusCal + run TLC")
    p_ver.add_argument("dir", nargs="?", default=".", help="Directory with Protocol.tla/.cfg (default: .)")
    p_ver.add_argument("--timeout", type=int, default=600, help="TLC timeout in seconds (default: 600)")
    p_ver.add_argument("--java-path", help="Path to Java 17 binary")
    p_ver.add_argument("--jar-path", help="Path to tla2tools.jar")
    p_ver.add_argument("--no-history", action="store_true", help="Skip archiving failed attempts to history/attempt_N/")
    p_ver.add_argument("--json", action="store_true", help="Emit a machine-readable JSON verdict on stdout (for CI/tooling)")

    # extract-states
    p_ext = sub.add_parser("extract-states", help="Extract IR v3 states from translated TLA+")
    p_ext.add_argument("dir", nargs="?", default=".", help="Directory with Protocol_translated.tla + ir.json (default: .)")
    p_ext.add_argument("--merge", action="store_true", help="Merge states into ir.json instead of writing states.json")
    p_ext.add_argument("--legacy", action="store_true", help="Use legacy regex-based TLA+ parser instead of tree-sitter PlusCal parser")
    p_ext.add_argument("--strict", action="store_true", help="Exit non-zero on warnings (orphan state_tasks / lint), not just parse errors")

    args = parser.parse_args()

    handlers = {
        "doctor": cmd_doctor,
        "init": cmd_init,
        "validate": cmd_validate,
        "scaffold": cmd_scaffold,
        "verify": cmd_verify,
        "extract-states": cmd_extract_states,
    }
    sys.exit(handlers[args.command](args))
