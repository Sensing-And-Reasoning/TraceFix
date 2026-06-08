"""CLI entry point: python -m tracefix.runtime.monitoring run --task 10M --workspace agent_workspace/10M [options]."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from datetime import datetime
from pathlib import Path

from tracefix.runtime.env_setup import load_repo_env

# Load repo-root .env so the in-process OpenAI-loop agents inherit OPENAI_API_KEY.
load_repo_env()


def _print_cost_summary(result, model: str) -> None:
    """Print per-agent and total token usage with estimated cost."""
    from tracefix.runtime.monitoring.cost import estimate_cost, format_cost
    print("\n=== Token Usage ===")
    total_in = total_out = 0
    for ar in result.agent_results:
        in_tok = getattr(ar, "input_tokens", 0)
        out_tok = getattr(ar, "output_tokens", 0)
        total_in += in_tok
        total_out += out_tok
        cost_str = f"  {format_cost(model, in_tok, out_tok)}" if (in_tok or out_tok) else ""
        print(f"  {ar.agent_id}: {in_tok:,} in + {out_tok:,} out{cost_str}")
    cost_str = f"  {format_cost(model, total_in, total_out)}" if (total_in or total_out) else ""
    print(f"  ─────────────────────────────────────────")
    print(f"  Total:  {total_in:,} in + {total_out:,} out{cost_str}")


def _print_trace(result):
    """Print per-agent tool call trace."""
    print("\n=== Tool Call Trace ===")
    for ar in result.agent_results:
        print(f"\n--- {ar.agent_id} ({ar.status}, {ar.steps} steps, {ar.duration:.1f}s) ---")
        if ar.error:
            print(f"  ERROR: {ar.error}")
        if not ar.trace:
            print("  (no tool calls recorded)")
            continue
        for tc in ar.trace:
            args_str = json.dumps(tc.arguments, ensure_ascii=False)
            status = tc.result.get("status", "?")
            # Compact result display
            if tc.tool_name == "receive_message":
                if status == "received":
                    detail = f'received label="{tc.result.get("label", "")}"'
                else:
                    detail = status
            elif tc.tool_name == "acquire_lock":
                detail = status
            elif tc.tool_name in ("send_message", "release_lock", "signal_done"):
                detail = status
            else:
                detail = status
            print(f"  R{tc.round:02d} {tc.tool_name}({args_str}) → {detail} [{tc.elapsed:.1f}s]")


def _cmd_run(args):
    """Run a task with RuntimeB."""
    from tracefix.runtime.monitoring.orchestrator import RuntimeB

    rt = RuntimeB(
        task_id=args.task,
        model=args.model,
        verbose=args.verbose,
        workspace=Path(args.workspace),
        live=args.live,
        live_port=args.live_port,
        scenario=args.scenario,
        difficulty=args.difficulty,
        tool_time=args.tool_time,
        seed=args.seed,
        max_rounds=args.max_rounds,
    )

    # Create timestamped results directory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output:
        results_dir = Path(args.output) / "tracefix.runtime.monitoring" / args.task / ts
    else:
        results_dir = rt.workspace / "results" / "tracefix.runtime.monitoring" / ts
    results_dir.mkdir(parents=True, exist_ok=True)

    # Tee stdout: capture for log file while still printing to terminal
    _real_stdout = sys.stdout
    _log_buf = io.StringIO()

    class _Tee:
        """Write to both terminal and buffer."""
        def write(self, s):
            _real_stdout.write(s)
            _log_buf.write(s)
        def flush(self):
            _real_stdout.flush()

    sys.stdout = _Tee()

    try:
        if args.verbose:
            print(f"[RuntimeB] Task: {args.task}, Model: {args.model}, "
                  f"Timeout: {args.timeout}s")
            print(f"[RuntimeB] Workspace: {rt.workspace}")
            print(f"[RuntimeB] Results dir: {results_dir}")
            print()

        result = asyncio.run(rt.run(timeout=args.timeout))

        # Print summary
        print("\n=== RuntimeB Result ===")
        if result.success:
            print(f"SUCCESS in {result.duration:.1f}s")
            for ar in result.agent_results:
                print(f"  {ar.agent_id}: {ar.steps} tool calls, "
                      f"{ar.duration:.1f}s")
        else:
            print(f"FAILED: {result.error or 'agent error'}")
            for ar in result.agent_results:
                status = ar.status
                if ar.error:
                    status += f" ({ar.error})"
                print(f"  {ar.agent_id}: {status}, {ar.steps} steps")

        # Always print trace
        _print_trace(result)

        # Print token usage and estimated cost
        _print_cost_summary(result, args.model)

        # Print sim results if sim was used
        if rt.sim is not None:
            _print_sim_summary(rt.sim)

        # Persist results to JSON
        from tracefix.runtime.monitoring.result_saver import save_run_result

        save_kwargs = dict(
            task_id=args.task,
            model=args.model,
            timeout=args.timeout,
            scenario=args.scenario,
            difficulty=args.difficulty,
            tool_time=args.tool_time,
            seed=args.seed,
        )
        if hasattr(rt, "_coord") and rt._coord is not None:
            save_kwargs["monitor_trace"] = rt._coord.monitor.trace
            if rt._coord.tracker:
                save_kwargs["tracker_states"] = rt._coord.tracker.current_states
                save_kwargs["tracker_violations"] = rt._coord.tracker.violations
        if rt.sim is not None:
            save_kwargs["sim"] = rt.sim

        save_run_result(results_dir / "run_result.json", result, **save_kwargs)

        # Always save HTML visualization
        _save_visualization(rt, result, results_dir,
                            open_browser=not args.no_open_html)

        print(f"\n[RuntimeB] All results saved to: {results_dir}")

    finally:
        sys.stdout = _real_stdout
        # Save captured log
        (results_dir / "run_log.txt").write_text(_log_buf.getvalue())


def _print_sim_summary(sim):
    """Print simulation progress and violations."""
    print("\n=== Simulation Summary ===")
    progress = sim.progress
    print(f"  Complete: {progress.get('all_complete', '?')}")
    for key, value in progress.items():
        if key == "all_complete":
            continue
        if isinstance(value, dict):
            for sub_key, sub_val in value.items():
                if isinstance(sub_val, bool):
                    print(f"  {key}/{sub_key}: {'done' if sub_val else 'pending'}")
                else:
                    print(f"  {key}/{sub_key}: {sub_val}")
        else:
            print(f"  {key}: {value}")

    if sim.has_violations:
        print(f"\n  Violations ({len(sim.violations)}):")
        for v in sim.violations:
            print(f"    [{v.violation_type}] {v.agent}/{v.tool}: {v.message}")
    else:
        print("\n  No violations detected")


def _save_visualization(rt, result, output_dir: Path, *, open_browser: bool = False):
    """Save HTML visualization, optionally open in browser."""
    from tracefix.runtime.monitoring.visualize import save_html

    ir_path = rt.workspace / "ir.json"
    with open(ir_path) as f:
        ir = json.load(f)

    output_path = (output_dir / "run_trace.html").resolve()
    title = f"Task {rt.task_id} | {rt.model}"
    save_html(ir, result, output_path, title=title, sim=rt.sim)
    print(f"\n[RuntimeB] Visualization saved: {output_path}")

    if open_browser:
        import webbrowser
        webbrowser.open(output_path.as_uri())


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="tracefix.runtime.monitoring",
        description="Architecture B: Monitoring runtime — agents follow pre-generated prompts",
    )
    sub = parser.add_subparsers(dest="command")

    run_cmd = sub.add_parser("run", help="Run a task")
    run_cmd.add_argument("--task", required=True, help="Task ID (e.g., 10M)")
    run_cmd.add_argument("--workspace", required=True,
                         help="Workspace path (e.g., agent_workspace/10M)")
    run_cmd.add_argument("--model", default="gpt-5-mini",
                         help="LLM model (default: gpt-5-mini)")
    run_cmd.add_argument("--timeout", type=float, default=180.0,
                         help="Timeout in seconds (default: 180)")
    run_cmd.add_argument("--max-rounds", type=int, default=50,
                         help="Max LLM rounds per agent (default: 50)")
    run_cmd.add_argument("--verbose", action="store_true",
                         help="Print per-agent debug info")
    run_cmd.add_argument("--no-open-html", action="store_true",
                         help="Don't open run_trace.html in browser after run (HTML is always saved)")
    run_cmd.add_argument("--live", action="store_true",
                         help="Open real-time visualization in browser during execution")
    run_cmd.add_argument("--live-port", type=int, default=8765,
                         help="Port for live visualization server (default: 8765)")
    # Failure injection (mutually exclusive)
    fail_group = run_cmd.add_mutually_exclusive_group()
    fail_group.add_argument("--difficulty", type=int, default=1,
                            help="Difficulty level 0-3 (0=easy, 1=medium, 2=hard, 3=nightmare). Default: 1")
    fail_group.add_argument("--scenario", type=int, default=None,
                            help="Deterministic retry depth: each decision fails N times then passes")
    # Orthogonal sim parameters
    run_cmd.add_argument("--tool-time", type=float, default=None,
                         help="Delay multiplier for domain tools (0=instant, 1=default, 2=double)")
    run_cmd.add_argument("--seed", type=int, default=None,
                         help="Random seed for reproducible sim-layer behavior")
    run_cmd.add_argument("--output", type=str, default=None,
                         help="Output root directory for results (default: {workspace}/results/)")

    args = parser.parse_args(argv)

    if args.command == "run":
        _cmd_run(args)
    else:
        parser.print_help()
        sys.exit(1)
