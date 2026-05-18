"""CLI entry point: python -m tracefix.runtime.enforcement {viz|run} <ir.json> [options]."""

import argparse
import asyncio
import io
import json
import subprocess
import sys
import webbrowser
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from tracefix.runtime.enforcement.topology import build_topology, load_ir


def _json_serializable(obj):
    """Convert sets to sorted lists for JSON serialization."""
    if isinstance(obj, set):
        return sorted(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _cmd_viz(args):
    """Visualize IR as HTML topology graph."""
    from tracefix.runtime.enforcement.visualize import save_html

    ir = _load(args.ir_file)
    topology = build_topology(ir)

    if args.json_output:
        data = asdict(topology)
        json.dump(data, sys.stdout, indent=2, default=_json_serializable)
        print()
        return

    output_path = args.output or Path(args.ir_file.stem + ".html")
    output_path = Path(output_path)
    save_html(topology, output_path, title=args.title)
    print(f"Written: {output_path}")

    try:
        subprocess.Popen(["open", str(output_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass


def _load_ir_for_run(args):
    """Load IR from --task directory or positional ir_file.

    Returns (ir, title, task_id, task_dir) where task_id is the directory name
    (e.g. "4A") used to load domain tools, or None.
    """
    if args.task:
        from tracefix.runtime.enforcement.loader import load_task
        task_dir = Path(args.task)
        try:
            ir = load_task(task_dir)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        title = args.title or task_dir.name
        task_id = task_dir.name  # e.g. "4A", "3E"
    elif args.ir_file:
        ir = _load(args.ir_file)
        title = args.title or args.ir_file.stem
        task_id = None
        task_dir = Path(args.ir_file).parent
    else:
        print("Error: provide either ir_file or --task", file=sys.stderr)
        sys.exit(1)
    return ir, title, task_id, task_dir


def _build_policy(args, ir, task_id: str | None = None):
    """Build execution policy from CLI args. Returns (policy, sim)."""
    sim = None
    if args.llm:
        from tracefix.runtime.enforcement.llm_policy import LLMPolicy
        prompts = ir.get("prompts", {})
        if not prompts:
            print("Warning: --llm specified but no prompts found in IR", file=sys.stderr)

        # Load domain tools if task_id is available
        tool_registry = None
        if task_id:
            tool_registry = _load_tool_registry(
                task_id,
                difficulty=getattr(args, "difficulty", 1),
                scenario=getattr(args, "scenario", None),
                tool_time=getattr(args, "tool_time", None),
                seed=args.seed,
            )
            if tool_registry and tool_registry._sim is not None:
                sim = tool_registry._sim

        return LLMPolicy(
            prompts=prompts,
            tool_registry=tool_registry,
            model=args.model,
            verbose=args.verbose,
        ), sim
    return None, sim


def _load_tool_registry(
    task_id: str,
    *,
    difficulty: int = 1,
    scenario: int | None = None,
    tool_time: float | None = None,
    seed: int | None = None,
):
    """Try to load a ToolRegistry for the given task_id.

    When a sim module exists for the task, instantiate it and configure
    failure injection (difficulty/scenario), delay multiplier, and seed.
    """
    try:
        import importlib as _imp

        from benchmark.tools._base import ToolConfig
        from benchmark.tools._registry import ToolRegistry

        # Zero delay for tracefix.runtime.enforcement — engine controls timing
        config = ToolConfig(min_delay=0, max_delay=0, fail_probability=0)

        # Auto-discover sim module (same pattern as tracefix.runtime.monitoring)
        sim = None
        try:
            sim_mod = _imp.import_module(
                f"benchmark.environments.{task_id}.sim")
            for attr in dir(sim_mod):
                obj = getattr(sim_mod, attr)
                if (isinstance(obj, type) and attr.endswith("Sim")
                        and obj.__module__ == sim_mod.__name__):
                    sim = obj()
                    break
            if sim is not None:
                if tool_time is not None:
                    sim._delay_multiplier = tool_time
                if seed is not None:
                    sim._seed = seed
                if scenario is not None:
                    sim.set_scenario_depth(scenario)
                else:
                    sim.set_difficulty(difficulty if difficulty is not None else 1)
        except (ModuleNotFoundError, ImportError):
            pass

        registry = ToolRegistry(task_id, config=config, sim=sim)
        mode = "sim" if sim else "dummy"
        print(f"Tools ({mode}): {', '.join(registry.tool_names)}")
        return registry
    except (FileNotFoundError, ImportError) as e:
        print(f"Warning: could not load tools for {task_id}: {e}", file=sys.stderr)
        return None


def _print_header(ir, title, args):
    """Print run header to stdout."""
    agents = [a["id"] for a in ir["agents"]]
    resources = ir.get("resources", [])
    channels = ir.get("channels", [])

    print(f"=== Protocol Execution: {title} ===")
    print(f"Agents: {', '.join(agents)}")
    if resources:
        parts = []
        for r in resources:
            if r["type"] == "Counter":
                parts.append(f"{r['id']} (Counter={r.get('config', {}).get('initial', 0)})")
            else:
                parts.append(f"{r['id']} ({r['type']})")
        print(f"Resources: {', '.join(parts)}")
    if channels:
        print(f"Channels: {', '.join(c['id'] for c in channels)}")
    if args.seed is not None:
        print(f"Seed: {args.seed}")
    if args.llm:
        print(f"Policy: LLM ({args.model})")
    # Sim parameters
    if getattr(args, "scenario", None) is not None:
        print(f"Scenario: depth={args.scenario}")
    elif getattr(args, "difficulty", None) is not None:
        print(f"Difficulty: {args.difficulty}")
    if getattr(args, "tool_time", None) is not None:
        print(f"Tool-time: {args.tool_time}x")
    if getattr(args, "live", False):
        print(f"Live: http://127.0.0.1:{args.port}")
    print()


def _print_result(result, args):
    """Print execution trace and result to stdout."""
    if not args.quiet:
        print("--- Execution Trace ---")
        for ev in result.trace:
            ops = ""
            if ev.guards or ev.effects:
                ops = "  " + " ".join(ev.guards + ev.effects)
            print(f"  [{ev.step:3d}] {ev.agent}: {ev.from_state} -> {ev.to_state}{ops}")
        print()

    # Per-agent summary
    from tracefix.runtime.enforcement.result_saver import _aggregate_agents
    agent_stats = _aggregate_agents(result)

    print("=== Result ===")
    if result.success:
        print(f"SUCCESS in {result.steps} steps ({result.duration:.1f}s)")
        for aid, stats in agent_stats.items():
            print(f"  {aid}: {stats['steps']} steps, {stats['tool_calls']} tool calls")
    else:
        print(f"FAILED: {result.error}")
        if result.trace:
            print(f"  ({result.steps} steps completed before failure)")
            for aid, stats in agent_stats.items():
                print(f"  {aid}: {stats['steps']} steps, {stats['tool_calls']} tool calls")


def _print_sim_summary(sim):
    """Print simulation progress and violations."""
    print("\n=== Simulation ===")
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
        print("  No violations")


def _cmd_run(args):
    """Execute an IR protocol and print the trace."""
    ir, title, task_id, task_dir = _load_ir_for_run(args)
    policy, sim = _build_policy(args, ir, task_id=task_id)
    _print_header(ir, title, args)

    # Determine workspace and results directory
    workspace = Path(args.workspace) if args.workspace else task_dir
    results_dir = None
    if args.llm:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if args.output:
            results_dir = Path(args.output) / "tracefix.runtime.enforcement" / (task_id or "unknown") / ts
        else:
            results_dir = workspace / "results" / "tracefix.runtime.enforcement" / ts
        results_dir.mkdir(parents=True, exist_ok=True)

    # Set up log teeing when saving results
    _real_stdout = sys.stdout
    _log_buf = io.StringIO() if results_dir else None

    class _Tee:
        """Write to both terminal and buffer."""
        def write(self, s):
            _real_stdout.write(s)
            _log_buf.write(s)
        def flush(self):
            _real_stdout.flush()
            _log_buf.flush()

    if _log_buf is not None:
        sys.stdout = _Tee()

    try:
        if getattr(args, "live", False):
            result = asyncio.run(_cmd_run_live(args, ir, title, policy, sim=sim))
        else:
            from tracefix.runtime.enforcement.engine import run_ir
            result = run_ir(ir, seed=args.seed, timeout=args.timeout, policy=policy)

        _print_result(result, args)

        # Print sim summary if available
        if sim is not None:
            _print_sim_summary(sim)

        # Save results when results_dir is set
        if results_dir is not None:
            _save_results(
                ir, result, results_dir,
                task_id=task_id or title,
                model=args.model,
                timeout=args.timeout,
                seed=args.seed,
                sim=sim,
                title=title,
                open_browser=not args.no_open_html,
                difficulty=getattr(args, "difficulty", 1),
                scenario=getattr(args, "scenario", None),
                tool_time=getattr(args, "tool_time", None),
            )
            print(f"\n[RuntimeA] All results saved to: {results_dir}")

    finally:
        if _log_buf is not None:
            sys.stdout = _real_stdout
            (results_dir / "run_log.txt").write_text(_log_buf.getvalue())


def _save_results(
    ir, result, results_dir, *,
    task_id, model, timeout, seed, sim, title,
    open_browser=False,
    difficulty=1, scenario=None, tool_time=None,
):
    """Save run_result.json and run_trace.html."""
    from tracefix.runtime.enforcement.result_saver import save_run_result
    from tracefix.runtime.enforcement.visualize import save_run_html

    # Save JSON
    save_run_result(
        results_dir / "run_result.json",
        result,
        task_id=task_id,
        model=model,
        timeout=timeout,
        seed=seed,
        sim=sim,
        difficulty=difficulty,
        scenario=scenario,
        tool_time=tool_time,
    )

    # Save HTML
    html_path = save_run_html(
        ir, result,
        results_dir / "run_trace.html",
        title=f"{title} | {model}" if model else title,
        sim=sim,
    )

    if open_browser:
        webbrowser.open(html_path.resolve().as_uri())


async def _cmd_run_live(args, ir, title, policy, sim=None):
    """Run protocol with live visualization server. Returns RunResult."""
    from tracefix.runtime.enforcement.event_bus import EventBus
    from tracefix.runtime.enforcement.live_server import start_live_server, stop_live_server
    from tracefix.runtime.enforcement.engine import run_protocol

    event_bus = EventBus()
    port = args.port

    # Start server
    server = await start_live_server(ir, event_bus, port=port, title=title)
    url = f"http://127.0.0.1:{port}"
    print(f"Live visualization: {url}")

    # Open browser
    webbrowser.open(url)

    # Small delay to let browser connect before events start
    await asyncio.sleep(0.5)

    # Start sim polling task (emits sim.update every 0.5s while running)
    poll_task = None
    if sim is not None:
        async def _poll_sim():
            while True:
                await asyncio.sleep(0.5)
                try:
                    await event_bus.emit("sim.update", _build_sim_data(sim))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
        poll_task = asyncio.create_task(_poll_sim())

    # Run protocol
    result = await run_protocol(
        ir, seed=args.seed, timeout=args.timeout,
        policy=policy, event_bus=event_bus,
    )

    # Stop polling and emit final sim state
    if poll_task is not None:
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass
        try:
            await event_bus.emit("sim.update", _build_sim_data(sim))
        except Exception:
            pass

    # Let final events flush to clients
    await asyncio.sleep(1.0)

    # Shutdown
    await event_bus.close()
    await stop_live_server(server)

    return result


def _build_sim_data(sim) -> dict:
    """Serialize sim.progress and sim.violations for SSE event."""
    progress: dict = {}
    try:
        raw = sim.progress
        for k, v in raw.items():
            progress[k] = dict(v) if isinstance(v, dict) else v
    except Exception:
        pass

    violations: list = []
    try:
        for v in sim.violations:
            violations.append({
                "type": getattr(v, "violation_type", "?"),
                "agent": getattr(v, "agent", ""),
                "tool": getattr(v, "tool", ""),
                "message": getattr(v, "message", ""),
            })
    except Exception:
        pass

    return {"progress": progress, "violations": violations}


def _load(path: Path) -> dict:
    try:
        return load_ir(path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="tracefix.runtime.enforcement",
        description="IR topology analysis, visualization, and execution",
    )
    sub = parser.add_subparsers(dest="command")

    # --- viz ---
    viz = sub.add_parser("viz", help="Visualize IR as HTML topology graph")
    viz.add_argument("ir_file", type=Path, help="Path to IR JSON file")
    viz.add_argument("-o", "--output", type=Path, default=None, help="Output HTML path")
    viz.add_argument("--json", action="store_true", dest="json_output", help="JSON output to stdout")
    viz.add_argument("--title", type=str, default="", help="HTML page title")

    # --- run ---
    run = sub.add_parser("run", help="Execute IR protocol and print trace")
    run.add_argument("ir_file", type=Path, nargs="?", default=None, help="Path to IR JSON file")
    run.add_argument("--task", type=str, default=None, help="Path to task directory (with ir.json + states.json)")
    run.add_argument("--seed", type=int, default=None, help="Random seed for deterministic runs")
    run.add_argument("--timeout", type=float, default=5.0, help="Timeout in seconds (default: 5)")
    run.add_argument("--title", type=str, default="", help="Protocol title")
    run.add_argument("-q", "--quiet", action="store_true", help="Suppress trace output")
    run.add_argument("--llm", action="store_true", help="Use LLM policy for decision points")
    run.add_argument("--model", type=str, default="gpt-4.1-mini", help="LLM model (default: gpt-4.1-mini)")
    run.add_argument("-v", "--verbose", action="store_true", help="Verbose LLM output")
    run.add_argument("--live", action="store_true", help="Launch real-time visualization in browser")
    run.add_argument("--port", type=int, default=8765, help="Live server port (default: 8765)")
    run.add_argument("--workspace", type=str, default=None, help="Workspace directory for results")
    run.add_argument("--no-open-html", action="store_true",
                     help="Don't open run_trace.html in browser (HTML is always saved with --llm)")
    # Failure injection (mutually exclusive)
    fail_group = run.add_mutually_exclusive_group()
    fail_group.add_argument("--difficulty", type=int, default=None,
                            help="Difficulty level 0-3 (0=easy, 1=medium, 2=hard, 3=nightmare). Default: 1")
    fail_group.add_argument("--scenario", type=int, default=None,
                            help="Deterministic retry depth: each decision fails N times then passes")
    # Orthogonal sim parameter
    run.add_argument("--tool-time", type=float, default=None,
                     help="Delay multiplier for domain tools (0=instant, 1=default, 2=double)")
    run.add_argument("--output", type=str, default=None,
                     help="Output root directory for results (default: {workspace}/results/)")

    args = parser.parse_args()

    if args.command == "viz":
        _cmd_viz(args)
    elif args.command == "run":
        _cmd_run(args)
    else:
        parser.print_help()
        sys.exit(1)
