"""CLI: run a tracefix workspace with OpenCode as the per-agent harness.

    python -m tracefix.runtime.opencode_adapter run \
        --task mas_research --workspace workspace/mas_research \
        --model openai/gpt-5.4-mini --opencode-bin opencode --live --verbose

Starts one in-process CoordinationService and drives one OpenCode process per
agent (each with a per-agent tracefix-coord MCP server). Mirrors the
``sdk_adapter`` CLI so a workspace can be run through either harness on the same
verified coordination layer.
"""

from __future__ import annotations

import argparse
import asyncio
import shlex
import sys

from tracefix.runtime.opencode_adapter.orchestrator import OpencodeOrchestrator
from tracefix.runtime.env_setup import load_repo_env

# Load the repo-root .env up front so the spawned opencode child processes inherit
# OPENAI_API_KEY / OPENROUTER_API_KEY — else every agent fails auth with 0 tool calls.
load_repo_env()


def _print_result(result, verbose: bool) -> None:
    print("\n=== OpenCode Adapter Result ===")
    print(f"{'SUCCESS' if result.success else 'INCOMPLETE'} in {result.duration:.1f}s")
    if getattr(result, "run_dir", ""):
        print(f"run snapshot: {result.run_dir}  (data-plane artifacts in output/)")
    for r in result.agent_results:
        line = (f"  {r['agent_id']}: {len(r.get('tool_calls', []))} tool calls, "
                f"{r.get('status')}")
        if r.get("error"):
            line += f" — {r['error']}"
        print(line)

    print("\n=== Monitoring ===")
    if result.state_violations:
        print(f"  state-machine violations: {len(result.state_violations)}")
        for v in result.state_violations[:10]:
            print(f"    ⚠ {v.get('agent')} @ {v.get('state')}: "
                  f"{v.get('operation')}({v.get('args')})")
    else:
        print("  clean — no protocol violations")
    if result.premature_dones:
        print(f"  premature signal_done: {result.premature_dones}")
    if result.corrections_exceeded:
        print(f"  correction cap exceeded (honest failure): {result.corrections_exceeded}")

    if verbose:
        print("\n=== Tool-call traces ===")
        for r in result.agent_results:
            print(f"--- {r['agent_id']} ({r.get('status')}) ---")
            for tc in r.get("tool_calls", []):
                rs = f" [{tc['result_status']}]" if tc.get("result_status") else ""
                print(f"  {tc.get('tool')} -> {tc.get('status')}{rs}")


def cmd_run(args: argparse.Namespace) -> int:
    opencode_cmd = shlex.split(args.opencode_bin) if args.opencode_bin else ["opencode"]
    orch = OpencodeOrchestrator(
        args.task, args.workspace,
        model=args.model, opencode_cmd=opencode_cmd,
        host=args.host, port=args.port, op_timeout_ms=args.op_timeout,
        timeout=args.timeout, start_stagger=args.start_stagger, verbose=args.verbose,
        live=args.live, live_port=args.live_port,
        live_warmup=args.live_warmup, live_hold=args.live_hold)
    result = asyncio.run(orch.run())
    _print_result(result, args.verbose)
    return 0 if result.success else 1


def main(argv=None) -> None:
    p = argparse.ArgumentParser(
        prog="python -m tracefix.runtime.opencode_adapter",
        description="Run a tracefix workspace with OpenCode as the per-agent harness.")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a verified workspace via OpenCode")
    run.add_argument("--task", required=True, help="Task id / label (e.g. mas_research)")
    run.add_argument("--workspace", required=True, help="Verified workspace path")
    run.add_argument("--model", default=None,
                     help="OpenCode model, provider/modelID (e.g. openai/gpt-5.4-mini)")
    run.add_argument("--opencode-bin", default="opencode",
                     help="opencode binary/command (shlex-split; e.g. 'opencode' or "
                          "'bun run /path/to/opencode/src/index.ts')")
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=8780,
                     help="CoordinationService port (default 8780)")
    run.add_argument("--op-timeout", type=int, default=120_000,
                     help="MCP timeout in ms (per-server + experimental; default 120000)")
    run.add_argument("--timeout", type=float, default=600.0,
                     help="Per-agent wall-clock cap in seconds (default 600)")
    run.add_argument("--start-stagger", type=float, default=10.0,
                     help="Seconds between launching each agent's OpenCode process, to "
                          "spread the per-instance cold-start/DB-migration (default 10)")
    run.add_argument("--verbose", action="store_true")
    run.add_argument("--live", action="store_true",
                     help="Real-time D3/SSE visualization in the browser")
    run.add_argument("--live-port", type=int, default=8765)
    run.add_argument("--live-warmup", type=float, default=4.0)
    run.add_argument("--live-hold", type=float, default=0.0)

    args = p.parse_args(argv)
    if args.command == "run":
        sys.exit(cmd_run(args))


if __name__ == "__main__":
    main()
