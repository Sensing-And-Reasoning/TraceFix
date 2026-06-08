"""CLI for the Claude Agent SDK adapter.

    python -m tracefix.runtime.sdk_adapter run --task 3E --workspace agent_workspace/3E
    python -m tracefix.runtime.sdk_adapter run --task 3E --workspace ws/3E \
        --model claude-sonnet-4-6 --builtins Read,Write,Edit,Bash --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
except ImportError:
    pass  # python-dotenv optional; SDK can also use the Claude CLI's own auth

from tracefix.runtime.sdk_adapter.orchestrator import SdkOrchestrator


def _print_result(result) -> None:
    print("\n=== SDK Adapter Result ===")
    verdict = "SUCCESS" if result.success else "INCOMPLETE"
    print(f"{verdict} in {result.duration:.1f}s")
    if getattr(result, "run_dir", ""):
        print(f"run snapshot: {result.run_dir}  (data-plane artifacts in output/)")
    for r in result.agent_results:
        print(f"  {r.agent_id}: {r.steps} tool calls, {r.status}, {r.duration:.1f}s"
              + (f" — {r.error}" if r.error else ""))

    # Monitoring conclusions — what the protocol monitor actually observed.
    print("\n=== Monitoring ===")
    sv = getattr(result, "state_violations", [])
    pd = getattr(result, "premature_dones", [])
    ce = getattr(result, "corrections_exceeded", [])
    print(f"  state-machine violations: {len(sv)}")
    for v in sv:
        print(f"    ⚠ {v.get('agent')} @ {v.get('state')}: "
              f"{v.get('operation')}({v.get('args')})")
    if pd:
        print(f"  premature signal_done: {', '.join(pd)}")
    if ce:
        print(f"  correction cap exceeded (honest failure): {', '.join(ce)}")
    if not sv and not pd and not ce:
        print("  clean — no protocol violations, no premature termination")

    print("\n=== Tool Call Trace ===")
    for r in result.agent_results:
        print(f"--- {r.agent_id} ({r.status}, {r.steps} steps, {r.duration:.1f}s) ---")
        for tc in r.trace:
            print(f"  R{tc.round:02d} {tc.tool_name}({tc.arguments}) "
                  f"-> {tc.result.get('status')} [{tc.elapsed:.2f}s]")


def cmd_run(args: argparse.Namespace) -> int:
    orch = SdkOrchestrator(
        task_id=args.task,
        workspace=args.workspace,
        model=args.model,
        builtins=[b.strip() for b in args.builtins.split(",") if b.strip()],
        max_rounds=args.max_rounds,
        verbose=args.verbose,
        scenario=args.scenario,
        difficulty=args.difficulty,
        tool_time=args.tool_time,
        seed=args.seed,
        coord_url=args.coord_url,
        live=args.live,
        live_port=args.live_port,
        live_warmup=args.live_warmup,
        live_hold=args.live_hold,
    )
    try:
        result = asyncio.run(orch.run(timeout=args.timeout))
    except ImportError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    _print_result(result)
    return 0 if result.success else 1


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tracefix.runtime.sdk_adapter",
        description="Drive tracefix-verified protocols with the Claude Agent SDK.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run a workspace with SDK-driven agents")
    p_run.add_argument("--task", required=True, help="Task ID (e.g. 3E)")
    p_run.add_argument("--workspace", required=True, help="Verified workspace path")
    p_run.add_argument("--model", default=None,
                       help="Model override (default: SDK/CLI default)")
    p_run.add_argument("--builtins", default="Read,Write,Edit",
                       help="Comma-separated SDK built-in tools to allow "
                            "(e.g. Read,Write,Edit,Bash). Empty to disable.")
    p_run.add_argument("--max-rounds", type=int, default=50,
                       help="Per-agent turn cap (default: 50)")
    p_run.add_argument("--timeout", type=float, default=180.0,
                       help="Global timeout in seconds (default: 180)")
    p_run.add_argument("--verbose", action="store_true")
    p_run.add_argument("--live", action="store_true",
                       help="Real-time D3/SSE visualization (in-process mode only); opens a browser")
    p_run.add_argument("--live-port", type=int, default=8765,
                       help="Port for the live view (default: 8765)")
    p_run.add_argument("--live-warmup", type=float, default=4.0,
                       help="Seconds to wait (after opening the browser) before agents start, "
                            "so the whole run is visible (default: 4)")
    p_run.add_argument("--live-hold", type=float, default=0.0,
                       help="Seconds to keep the live view up AFTER the run, for inspection "
                            "(default: 0 = stop when the run ends)")
    p_run.add_argument("--coord-url", default=None,
                       help="Distributed mode: URL of a running CoordinationService "
                            "(e.g. http://127.0.0.1:8780). Each agent talks to it via "
                            "a CoordClient instead of a shared in-process context. "
                            "Start the service with `python -m tracefix.runtime.coordination`.")
    # Sim failure injection (scenarios 12-16), mirrors the monitoring CLI.
    p_run.add_argument("--scenario", type=int, default=None)
    p_run.add_argument("--difficulty", type=int, default=1)
    p_run.add_argument("--tool-time", type=float, default=None)
    p_run.add_argument("--seed", type=int, default=None)

    args = parser.parse_args(argv)
    handlers = {"run": cmd_run}
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
