"""``tracefix`` — one command to run a TLA+-verified workspace as a live MAS.

This is the front door for the runtime half. Point it at a workspace the
``/tla-verify-pluscal`` skill produced and it starts the whole multi-agent system
on the verified coordination layer:

    tracefix run --workspace workspace/my_task

Defaults to the **opencode** harness (tracefix's per-agent OpenCode harness).
Switch with ``--harness {opencode,sdk,monitoring}``. Common flags (--model,
--live, --verbose) are forwarded; any harness-specific flags after them are
passed straight through to that harness's ``run`` command, e.g.::

    tracefix run --workspace ws --harness sdk --builtins Read,Write,Edit,Bash
    tracefix run --workspace ws --opencode-bin 'bun run /path/to/opencode'
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from tracefix.runtime.workspace_layout import spec_path

# harness name → CLI module exposing main(argv)
_HARNESS_MODULES = {
    "opencode": "tracefix.runtime.opencode_adapter.cli",
    "sdk": "tracefix.runtime.sdk_adapter.cli",
    "monitoring": "tracefix.runtime.monitoring.cli",
}


def _derive_task(workspace: str, task: str | None) -> str:
    """Task id/label — explicit wins, else the workspace folder name."""
    if task:
        return task
    return Path(workspace).resolve().name or "custom"


def _has_prompts(ws: Path) -> bool:
    # orchestrators look for prompts/runtime_b/ then prompts/ (flat fallback)
    for sub in ("prompts/runtime_b", "prompts"):
        d = ws / sub
        if d.is_dir() and any(d.glob("*.md")):
            return True
    return False


def _preflight(workspace: str) -> list[str]:
    """Human-readable blockers (empty list = ready to run)."""
    ws = Path(workspace)
    if not ws.exists():
        return [f"workspace not found: {workspace}"]
    problems = []
    if not spec_path(ws, "ir.json").exists():
        problems.append("missing ir.json (expected spec/ir.json, or the workspace root)")
    if not _has_prompts(ws):
        problems.append("no per-agent prompts found (expected prompts/runtime_b/<agent>.md)")
    return problems


def cmd_run(args: argparse.Namespace, extra: list[str]) -> int:
    problems = _preflight(args.workspace)
    if problems:
        print("Cannot run this workspace yet:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print(
            "\nProduce a runnable workspace with the /tla-verify-pluscal skill "
            "(it designs + verifies the protocol and generates the prompts), "
            "then re-run this command.",
            file=sys.stderr,
        )
        return 2

    ws = Path(args.workspace)
    if not spec_path(ws, "states.json").exists():
        print(
            "note: no states.json — signal_done() will be ungated (per-agent FSM "
            "checks off). Run `tla-verify-pluscal extract-states` for full enforcement.",
            file=sys.stderr,
        )

    task = _derive_task(args.workspace, args.task)
    argv = ["run", "--task", task, "--workspace", args.workspace]
    if args.model:
        argv += ["--model", args.model]
    if args.live:
        argv += ["--live"]
    if args.verbose:
        argv += ["--verbose"]
    argv += extra  # harness-specific passthrough (e.g. --opencode-bin, --builtins)

    mod = importlib.import_module(_HARNESS_MODULES[args.harness])
    if args.verbose:
        print(f"[tracefix] harness={args.harness} task={task} "
              f"workspace={args.workspace}", file=sys.stderr)
    try:
        rc = mod.main(argv)
    except SystemExit as e:  # sdk/opencode mains sys.exit(code)
        rc = e.code
    if rc is None:
        return 0
    return rc if isinstance(rc, int) else 1


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="tracefix",
        description="Run a TLA+-verified multi-agent workspace on the verified "
                    "coordination layer.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser(
        "run",
        help="Run a verified workspace (default harness: opencode)",
        description="Run a verified workspace through an agent harness. Unknown "
                    "flags are passed through to the selected harness.",
    )
    run.add_argument("--workspace", required=True,
                     help="Path to a verified workspace (spec/ir.json + prompts/)")
    run.add_argument("--harness", choices=list(_HARNESS_MODULES), default="opencode",
                     help="Agent harness (default: opencode)")
    run.add_argument("--task", default=None,
                     help="Task id/label (default: the workspace folder name)")
    run.add_argument("--model", default=None,
                     help="Model override (the harness default if omitted)")
    run.add_argument("--live", action="store_true",
                     help="Real-time D3/SSE visualization in the browser")
    run.add_argument("--verbose", action="store_true")

    args, extra = parser.parse_known_args(argv)
    if args.command == "run":
        sys.exit(cmd_run(args, extra))


if __name__ == "__main__":
    main()
