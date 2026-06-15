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


def resolve_init_dir(dir_arg: str) -> Path:
    """Where `init` puts a workspace. A bare name (no path separator) goes under the
    gitignored workspace/ root with a timestamp suffix, so EVERY design run gets a
    fresh directory — designs never silently iterate on (or overwrite) an older
    workspace with the same name. An explicit path is used as-is (escape hatch for
    tests/examples that need an exact location)."""
    out = Path(dir_arg)
    if out.parent != Path("."):
        return out
    from datetime import datetime
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fresh = Path("workspace") / f"{out.name}_{stamp}"
    n = 2
    while fresh.exists():  # same name + same second (e.g. parallel runs)
        fresh = Path("workspace") / f"{out.name}_{stamp}_{n}"
        n += 1
    return fresh


def cmd_init(args: argparse.Namespace) -> int:
    """Scaffold a custom-task workspace: description.md + ir.json stub (+ tools.json)."""
    out = resolve_init_dir(args.dir)
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


def _workspace_root(search_dir: Path) -> Path:
    """The workspace root holding inputs (description.md, tools.json). extract-states
    runs against `spec/`, so the root is its parent; a flat workspace is its own root."""
    return search_dir.parent if search_dir.name == "spec" else search_dir


def _generate_domain_tools(search_dir: Path, tla_content: str, states: list[dict]) -> None:
    """Lift `[tool: ...]`-tagged `\\* domain:` steps into a workspace `tools.json`
    (schemas + per-agent `agent_ids`) plus impl scaffolds: a `tools_impl.py` stub for
    `impl: local` tools (auto-wrapped as MCP by the runtime) and an `mcp.json` stub
    for `impl: external` tools (bind to a real service). Derived from the verified
    PlusCal, so `tools.json` is regenerated each run; hand-filled stubs are preserved."""
    from tracefix.pipeline.pipeline.pluscal_parser import extract_domain_tools
    tools = extract_domain_tools(tla_content, states)
    if not tools:
        return
    root = _workspace_root(search_dir)
    (root / "tools.json").write_text(json.dumps(tools, indent=2) + "\n")
    local = [t["function"]["name"] for t in tools if t["function"].get("x-impl") == "local"]
    external = [t["function"] for t in tools if t["function"].get("x-impl") == "external"]
    print(f"OK — wrote {len(tools)} domain tool schema(s) to {root / 'tools.json'} "
          f"({len(local)} local, {len(external)} external)")
    for t in tools:
        fn = t["function"]
        print(f"  - {fn['name']}({', '.join(fn['parameters']['properties'])}) "
              f"[{fn.get('x-impl')}] → {', '.join(fn['agent_ids']) or '(unassigned)'}")

    # impl: local → Python stub (preserve a user's filled-in version)
    if local:
        impl_path = root / "tools_impl.py"
        if impl_path.exists():
            print(f"  (kept existing {impl_path}; fill impls for: {', '.join(local)})")
        else:
            lines = ['"""Domain tool implementations (local). Fill each function body;',
                     'the runtime auto-wraps these as a per-agent MCP server. Return a',
                     'JSON-serializable dict."""', "", "from __future__ import annotations", ""]
            for t in tools:
                fn = t["function"]
                if fn.get("x-impl") != "local":
                    continue
                params = list(fn["parameters"]["properties"])
                sig = ", ".join(params)
                lines += [f"def {fn['name']}({sig}):",
                          f"    \"\"\"{fn['description']}\"\"\"",
                          "    raise NotImplementedError(\"fill in this domain tool\")", ""]
            impl_path.write_text("\n".join(lines))
            print(f"  - wrote stub {impl_path} (fill: {', '.join(local)})")

    # impl: external → mcp.json stub (preserve a user's bound version)
    if external:
        mcp_path = root / "mcp.json"
        if mcp_path.exists():
            print(f"  (kept existing {mcp_path}; bind servers for: "
                  f"{', '.join(f['name'] for f in external)})")
        else:
            mcp = {"mcpServers": {
                f"{f['name']}_service": {
                    "command": "<command or url for the real service>",
                    "args": [],
                    "tools": [f["name"]],
                    "agent_ids": f["agent_ids"],
                } for f in external}}
            mcp_path.write_text(json.dumps(mcp, indent=2) + "\n")
            print(f"  - wrote stub {mcp_path} (bind: "
                  f"{', '.join(f['name'] for f in external)})")


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

    # Lift any [tool: ...]-tagged domain steps into a workspace tools.json + impl
    # scaffolds (no-op when the design used only builtins — i.e. no tags), and tag
    # the owning states so prompt-gen can emit explicit `Call <tool>(...)` steps.
    from tracefix.pipeline.pipeline.pluscal_parser import annotate_state_tools
    annotate_state_tools(result.states, tla_content)
    _generate_domain_tools(search_dir, tla_content, result.states)

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
# Design guide (single source of design knowledge)
# ---------------------------------------------------------------------------
#
# The design WORKFLOW + detailed patterns live in ONE place — the skill
# (.claude/skills/tla-verify-pluscal/SKILL.md + references, and tla-prompt-gen
# for Phase 5). Three callers consume it: the Claude Code skill (reads the files
# directly), `tracefix design` headless (reads them by path), and the TUI
# `designer` agent (which runs anywhere and cannot assume the files are present).
# `tla-verify-pluscal guide` is how the TUI — and anything else on PATH — pulls
# the SAME source instead of carrying a thinner private copy that drifts.

_SKILL_DESIGN = Path(".claude/skills/tla-verify-pluscal")
_SKILL_PROMPTS = Path(".claude/skills/tla-prompt-gen")
#: guide section -> file under the relevant skill dir
_GUIDE_SECTIONS = {
    "pluscal": (_SKILL_DESIGN, "references/pluscal-guide.md"),
    "schema": (_SKILL_DESIGN, "references/schema-and-examples.md"),
    "plan": (_SKILL_DESIGN, "references/coordination-plan.md"),
    "prompts": (_SKILL_PROMPTS, "SKILL.md"),
}


def _strip_frontmatter(text: str) -> str:
    """Drop a leading YAML frontmatter block (skill invocation metadata)."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


def _find_skill_root() -> Path | None:
    """Locate the directory that holds `.claude/skills/`. Resolve from THIS
    file first (works wherever tracefix is installed editable, regardless of
    cwd — so the TUI designer finds it even when run in the user's own
    project), then fall back to walking up from cwd."""
    for base in Path(__file__).resolve().parents:
        if (base / _SKILL_DESIGN / "SKILL.md").exists():
            return base
    for base in [Path.cwd(), *Path.cwd().parents]:
        if (base / _SKILL_DESIGN / "SKILL.md").exists():
            return base
    return None


def cmd_guide(args: argparse.Namespace) -> int:
    """Print the design knowledge (single source). No args → the full
    design+verify workflow (SKILL.md with its references inlined); a section
    name → just that reference. Consumed by the TUI designer via bash."""
    root = _find_skill_root()
    if root is None:
        print("tla-verify-pluscal guide: could not locate the skill files "
              "(.claude/skills/tla-verify-pluscal/). Reinstall tracefix (pip install -e .) "
              "or run from the repo.", file=sys.stderr)
        return 1

    section = getattr(args, "section", None)
    if section:
        skill_dir, rel = _GUIDE_SECTIONS[section]
        f = root / skill_dir / rel
        if not f.exists():
            print(f"guide section file missing: {f}", file=sys.stderr)
            return 1
        sys.stdout.write(_strip_frontmatter(f.read_text()) if f.name == "SKILL.md"
                         else f.read_text())
        return 0

    # Default: the design+verify workflow + its references, inlined in one shot.
    out = [_strip_frontmatter((root / _SKILL_DESIGN / "SKILL.md").read_text())]
    for name in ("schema", "pluscal", "plan"):
        skill_dir, rel = _GUIDE_SECTIONS[name]
        f = root / skill_dir / rel
        if f.exists():
            out.append(f"\n\n===== reference: {name} =====\n\n{f.read_text()}")
    sys.stdout.write("\n".join(out) + "\n")
    return 0


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
    p_ini.add_argument("dir", help="Workspace name (a bare name is created under workspace/ "
                                   "with a timestamp suffix — every init is a fresh dir; "
                                   "an explicit path is used as-is)")
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

    # guide
    p_gui = sub.add_parser("guide", help="Print the design knowledge (single source for the TUI designer)")
    p_gui.add_argument("section", nargs="?", choices=sorted(_GUIDE_SECTIONS),
                       help="Print only one reference (default: the full design+verify workflow + references)")

    args = parser.parse_args()

    handlers = {
        "doctor": cmd_doctor,
        "init": cmd_init,
        "validate": cmd_validate,
        "scaffold": cmd_scaffold,
        "verify": cmd_verify,
        "extract-states": cmd_extract_states,
        "guide": cmd_guide,
    }
    sys.exit(handlers[args.command](args))
