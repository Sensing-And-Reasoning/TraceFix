"""CLI entry point for the Agentic TLA+ Verification Agent.

Usage:
    # Verify a custom task
    python -m tracefix.pipeline --task "Design a 2PC protocol with coordinator and 2 banks"

    # Run a benchmark task (full Phase 1-5 pipeline)
    python -m tracefix.pipeline --benchmark 1E
    python -m tracefix.pipeline --benchmark 1E 2M 5H

    # Run all benchmark tasks
    python -m tracefix.pipeline --benchmark-all

    # Phase 5 only: generate prompts from an already-verified workspace
    # (mirror of the /tla-prompt-gen skill)
    python -m tracefix.pipeline --prompt-gen-only agent_workspace/workspace/claude46_run_1/3E

    # Filter by difficulty and/or scenario
    python -m tracefix.pipeline --benchmark-all --difficulty E --parallel 3
    python -m tracefix.pipeline --benchmark-all --difficulty H --scenario 1 2
    python -m tracefix.pipeline --benchmark-all --scenario 3

    # Options
    python -m tracefix.pipeline --benchmark 1E --model gpt-5 --provider openai
    python -m tracefix.pipeline --benchmark 1E --provider openrouter --model minimax/minimax-m2.5
    python -m tracefix.pipeline --benchmark 1E --max-turns 15 --verbose
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from tracefix.pipeline.loop import AgentLoop
from tracefix.pipeline.prompts import SYSTEM_PROMPT, PROMPT_GEN_SYSTEM_PROMPT
from tracefix.pipeline.session import SessionRecord, estimate_run_cost, format_run_cost
from tracefix.pipeline.tool_client import ToolClient
from tracefix.pipeline.tools import TOOL_SCHEMAS
from tracefix.pipeline.workspace import Workspace
from tracefix.pipeline.pipeline.llm_client import LLMConfig


def _build_config(args: argparse.Namespace) -> LLMConfig:
    """Build LLMConfig from CLI args."""
    provider = args.provider

    # Resolve API key per provider
    if provider == "openrouter":
        api_key = args.api_key or os.environ.get("OPENROUTER_API_KEY", "")
    elif provider == "anthropic":
        api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    else:
        api_key = args.api_key or os.environ.get("OPENAI_API_KEY", "")

    # reasoning_effort: default "high" for openai only; "" for others unless explicit
    if args.reasoning_effort is not None:
        reasoning_effort = args.reasoning_effort
    elif provider == "openai":
        reasoning_effort = "high"
    else:
        reasoning_effort = ""

    return LLMConfig(
        provider=provider,
        model=args.model,
        api_key=api_key,
        reasoning_effort=reasoning_effort,
        thinking_budget=args.thinking_budget if provider == "anthropic" else 0,
        max_tokens=args.max_tokens,
        base_url="https://openrouter.ai/api/v1" if provider == "openrouter" else "",
    )


def _run_single(
    task_desc: str,
    task_id: str | None,
    config: LLMConfig,
    args: argparse.Namespace,
    workspaces_dir: str = "tracefix.pipeline/results/default/workspaces",
) -> tuple[str, Workspace]:
    """Run the agent on a single task. Returns (final_text, workspace)."""
    workspace = Workspace(base_dir=workspaces_dir)
    tool_client = ToolClient(config, TOOL_SCHEMAS)

    # Summarizer: same provider, cheap model (disabled with --no-summarize)
    summarizer_config = None
    if not args.no_summarize:
        summarizer_models = {
            "openai": "gpt-4.1-mini",
            "anthropic": "claude-haiku-4-5-20251001",
            "openrouter": "openai/gpt-4.1-mini",
        }
        summarizer_config = LLMConfig(
            provider=config.provider,
            model=summarizer_models.get(config.provider, "gpt-4.1-mini"),
            api_key=config.api_key,
            reasoning_effort="",
            temperature=0.3,
            max_tokens=2048,
            base_url=config.base_url,
        )

    # Prepare incremental session saver
    start = datetime.now()
    config_dict = {
        "provider": config.provider,
        "model": config.model,
        "api_key": config.api_key,
        "reasoning_effort": config.reasoning_effort,
        "thinking_budget": config.thinking_budget,
        "summarizer_model": summarizer_config.model if summarizer_config else "",
    }

    def _save_session_incremental(loop_ref: "AgentLoop") -> None:
        """Save session.json after each turn so it survives crashes."""
        session = SessionRecord.create(
            config=config_dict,
            workspace=workspace,
            messages=loop_ref.messages,
            final_text="(in progress)",
            start_time=start,
            task_id=task_id,
        )
        session.save(workspace)

    loop = AgentLoop(
        tool_client=tool_client,
        workspace=workspace,
        system_prompt=SYSTEM_PROMPT,
        max_turns=args.max_turns,
        verbose=args.verbose,
        summarizer_config=summarizer_config,
        on_turn_end=_save_session_incremental if not args.no_save else None,
    )

    # Build user message
    if task_id:
        user_msg = (
            f"Load benchmark task '{task_id}' and verify its coordination protocol.\n\n"
            f"Follow the 3-phase Recommended Workflow in the system prompt.\n"
            f"Key reminders: one channel per directed pair with labels, "
            f"loops are unbounded (NO Counter for loop bounds), "
            f"use think() before each step."
        )
    else:
        # Write task description to workspace
        workspace.write_file("task.md", task_desc)
        user_msg = (
            f"Verify the following coordination task:\n\n{task_desc}\n\n"
            f"Follow the 3-phase Recommended Workflow in the system prompt.\n"
            f"Key reminders: one channel per directed pair with labels, "
            f"loops are unbounded (NO Counter for loop bounds), "
            f"use think() before each step."
        )

    final_text = loop.run(user_msg)

    # Final session save with actual final_text
    if not args.no_save:
        session = SessionRecord.create(
            config=config_dict,
            workspace=workspace,
            messages=loop.messages,
            final_text=final_text,
            start_time=start,
            task_id=task_id,
        )
        filepath = session.save(workspace)
        print(f"\nSession saved to: {filepath}", file=sys.stderr)

    return final_text, workspace


def _run_prompt_gen(
    workspace_path: str,
    config: LLMConfig,
    args: argparse.Namespace,
) -> tuple[str, Workspace, str]:
    """Phase 5 only: generate per-agent prompts from an already-verified workspace.

    The workspace directory must already contain ir.json, states.json, Protocol.tla,
    and ideally summary.json + tools.json.
    """
    ws_path = Path(workspace_path).expanduser().resolve()
    if not ws_path.is_dir():
        raise SystemExit(f"--prompt-gen-only: workspace directory not found: {ws_path}")

    required = ["ir.json", "states.json", "Protocol.tla"]
    missing = [f for f in required if not (ws_path / f).exists()]
    if missing:
        raise SystemExit(
            f"--prompt-gen-only: workspace is missing required files: {', '.join(missing)}\n"
            f"Run /tla-verify-pluscal (or the full agent pipeline) first."
        )

    # Reuse the existing directory as-is: base_dir = parent, session_id = name.
    workspace = Workspace(session_id=ws_path.name, base_dir=str(ws_path.parent))
    tool_client = ToolClient(config, TOOL_SCHEMAS)

    summarizer_config = None
    if not args.no_summarize:
        summarizer_models = {
            "openai": "gpt-4.1-mini",
            "anthropic": "claude-haiku-4-5-20251001",
            "openrouter": "openai/gpt-4.1-mini",
        }
        summarizer_config = LLMConfig(
            provider=config.provider,
            model=summarizer_models.get(config.provider, "gpt-4.1-mini"),
            api_key=config.api_key,
            reasoning_effort="",
            temperature=0.3,
            max_tokens=2048,
            base_url=config.base_url,
        )

    loop = AgentLoop(
        tool_client=tool_client,
        workspace=workspace,
        system_prompt=PROMPT_GEN_SYSTEM_PROMPT,
        max_turns=args.max_turns,
        verbose=args.verbose,
        summarizer_config=summarizer_config,
    )

    user_msg = (
        f"Generate Runtime A and Runtime B per-agent prompts from this verified workspace.\n\n"
        f"Workspace root: {ws_path}\n\n"
        f"Follow the Workflow in the system prompt:\n"
        f"  Step 1: gather inputs (ir.json, states.json, Protocol.tla, summary.json, tools.json, task.md)\n"
        f"  Step 2: generate ALL Runtime B prompts first (2a inventory → 2b mapping → 2c prose → 2d verify)\n"
        f"  Step 3: generate Runtime A prompts by simplification, then run the Runtime A checklist\n"
        f"  Step 4: report the generated files."
    )

    final_text = loop.run(user_msg)
    summarizer_model = summarizer_config.model if summarizer_config else ""
    return final_text, workspace, summarizer_model


def _resolve_benchmark_runs(args: argparse.Namespace) -> list[tuple[str, int]]:
    """Return (task_id, trial) pairs to run."""
    from benchmark.loader import list_task_ids

    # Step 1: Resolve task IDs
    if args.benchmark:
        task_ids = args.benchmark
    else:
        # --benchmark-all: start with all, then filter
        task_ids = list_task_ids()
        if args.difficulty:
            allowed = {d.upper() for d in args.difficulty}
            task_ids = [tid for tid in task_ids if tid[-1] in allowed]
        if args.scenario:
            allowed = set(args.scenario)
            task_ids = [tid for tid in task_ids if tid[:-1] in allowed]

    # Step 2: Resolve trials
    trials = max(1, getattr(args, "trials", 1))

    # Step 3: Cross-product
    return [(tid, t) for tid in task_ids for t in range(1, trials + 1)]


_print_lock = threading.Lock()


def _run_and_collect(
    task_id: str,
    config: LLMConfig,
    args: argparse.Namespace,
    trial: int = 1,
    show_trial: bool = False,
    workspaces_dir: str = "tracefix.pipeline/results/default/workspaces",
    summarizer_model: str = "",
) -> dict:
    """Run one task, return result dict. Thread-safe."""
    parts = [task_id]
    if show_trial:
        parts.append(f"t{trial}")
    run_label = "/".join(parts)
    try:
        final_text, workspace = _run_single("", task_id, config, args, workspaces_dir=workspaces_dir)
        r = workspace.result
        cost = estimate_run_cost(workspace, config.model, summarizer_model)
        entry = {
            "task_id": task_id,
            "trial": trial,
            "passed": r.final_passed,
            "repairs": workspace.repair_count,
            "tools": workspace.total_tool_calls,
            "violation": r.tlc_violation_type,
            "passed_at": r.passed_at_repair,
            "workspace": workspace.root,
            "tokens": (
                workspace.total_prompt_tokens + workspace.total_completion_tokens
                + workspace.summarizer_prompt_tokens + workspace.summarizer_completion_tokens
            ),
            "cost_usd": cost["total_cost_usd"],
            "cost_known": cost["cost_known"],
        }
    except Exception as e:
        with _print_lock:
            print(f"  {run_label}: ERROR - {e}", file=sys.stderr)
        entry = {
            "task_id": task_id,
            "trial": trial,
            "passed": False,
            "repairs": 0,
            "tools": 0,
            "violation": "error",
            "passed_at": -1,
            "workspace": None,
            "tokens": 0,
            "cost_usd": 0.0,
            "cost_known": False,
        }
        return entry

    status = "PASS" if entry["passed"] else "FAIL"
    with _print_lock:
        print(
            f"  {run_label}: {status}  "
            f"({entry['tokens']:,} tok, ${entry['cost_usd']:.4f})",
            file=sys.stderr,
        )
    return entry


def main():
    parser = argparse.ArgumentParser(
        description="Agentic TLA+ Verification Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Task input (mutually exclusive)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task", type=str, help="Natural language task description")
    group.add_argument("--benchmark", nargs="+", help="Benchmark task ID(s)")
    group.add_argument(
        "--benchmark-all", action="store_true", help="Run all benchmark tasks"
    )
    group.add_argument(
        "--prompt-gen-only",
        metavar="WORKSPACE",
        type=str,
        help=(
            "Path to an already-verified workspace (must contain ir.json, states.json, "
            "Protocol.tla, summary.json, tools.json). Runs Phase 5 only: generate "
            "prompts/runtime_a/ and prompts/runtime_b/ per-agent prompts."
        ),
    )

    # LLM config
    parser.add_argument(
        "--provider", default="openai", choices=["openai", "anthropic", "openrouter"]
    )
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--api-key", default=None, help="API key (or set env var)")
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument("--thinking-budget", type=int, default=0)
    parser.add_argument("--max-tokens", type=int, default=32768)

    # Benchmark config
    parser.add_argument(
        "--difficulty",
        nargs="+",
        choices=["E", "M", "H"],
        help="Filter by difficulty (benchmark-all only)",
    )
    parser.add_argument(
        "--scenario",
        nargs="+",
        choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"],
        help="Filter by scenario number (benchmark-all only)",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="Number of trials per task (default: 1)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Number of tasks to run concurrently (default: 1)",
    )

    # Agent config
    parser.add_argument("--max-turns", type=int, default=60)

    # Flags
    parser.add_argument(
        "--verbose", action="store_true", help="Print tool calls to stderr"
    )
    parser.add_argument(
        "--no-save", action="store_true", help="Don't save session JSON"
    )
    parser.add_argument(
        "--no-summarize",
        action="store_true",
        help="Disable LLM-based context summarization (use truncation fallback)",
    )

    args = parser.parse_args()
    config = _build_config(args)

    if args.prompt_gen_only:
        # Phase 5 only: reuse the caller's workspace, no experiment dir.
        final_text, workspace, summarizer_model = _run_prompt_gen(
            args.prompt_gen_only, config, args,
        )
        print(f"\n{'='*60}")
        print(final_text)
        print(f"{'='*60}")
        cost = estimate_run_cost(workspace, config.model, summarizer_model)
        print(format_run_cost(cost))
        print(f"Workspace: {workspace.root}")
        return

    # Create experiment directory: tracefix.pipeline/results/<timestamp>/workspaces/
    experiment_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_dir = Path("tracefix.pipeline/results") / experiment_ts
    workspaces_dir = str(experiment_dir / "workspaces")
    print(f"Experiment dir: {experiment_dir}", file=sys.stderr)

    # Derive the summarizer model the same way _run_single does, for cost accounting.
    summarizer_model_hint = ""
    if not args.no_summarize:
        summarizer_model_hint = {
            "openai": "gpt-4.1-mini",
            "anthropic": "claude-haiku-4-5-20251001",
            "openrouter": "openai/gpt-4.1-mini",
        }.get(config.provider, "gpt-4.1-mini")

    if args.task:
        # Single custom task
        final_text, workspace = _run_single(args.task, None, config, args, workspaces_dir=workspaces_dir)
        print(f"\n{'='*60}")
        print(final_text)
        print(f"{'='*60}")
        print(
            f"Tool calls: {workspace.total_tool_calls} | "
            f"Inner LLM calls: {workspace.total_inner_llm_calls} | "
            f"Repairs: {workspace.repair_count}"
        )
        cost = estimate_run_cost(workspace, config.model, summarizer_model_hint)
        print(format_run_cost(cost))
        print(f"Workspace: {workspace.root}")

    elif args.benchmark or args.benchmark_all:
        # Resolve (task_id, trial) pairs to run
        runs = _resolve_benchmark_runs(args)
        show_trial = args.trials > 1
        parallel = max(1, args.parallel)

        if not runs:
            print("No tasks matched the given filters.", file=sys.stderr)
            sys.exit(1)

        # Deduplicate labels for display
        unique_tasks = sorted(set(tid for tid, _ in runs))
        trials_str = f", trials={args.trials}" if show_trial else ""
        print(
            f"Running {len(runs)} run(s) across {len(unique_tasks)} task(s) "
            f"(parallel={parallel}{trials_str}): {', '.join(unique_tasks)}",
            file=sys.stderr,
        )

        results: list[dict] = []
        if parallel == 1:
            # Sequential (no threading overhead)
            for tid, trial in runs:
                parts = [tid]
                if show_trial:
                    parts.append(f"t{trial}")
                label = "/".join(parts)
                print(f"\n{'='*60}", file=sys.stderr)
                print(f"Running: {label}", file=sys.stderr)
                print(f"{'='*60}", file=sys.stderr)
                entry = _run_and_collect(
                    tid, config, args,
                    trial=trial, show_trial=show_trial,
                    workspaces_dir=workspaces_dir,
                    summarizer_model=summarizer_model_hint,
                )
                results.append(entry)
        else:
            # Parallel execution
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                future_to_idx = {
                    pool.submit(
                        _run_and_collect, tid, config, args,
                        trial, show_trial, workspaces_dir,
                        summarizer_model_hint,
                    ): i
                    for i, (tid, trial) in enumerate(runs)
                }
                indexed_results: list[tuple[int, dict]] = []
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    indexed_results.append((idx, future.result()))
                # Preserve original order
                indexed_results.sort(key=lambda x: x[0])
                results = [entry for _, entry in indexed_results]

        # Summary table
        header = (
            f"{'Task ID':<10}"
            + (f" {'Trial':>6}" if show_trial else "")
            + f" {'Pass':>6} {'Repairs':>8} {'Tools':>6}"
            + f"  {'Violation':<14} {'Passed@':>8}"
            + f" {'Tokens':>10} {'Cost ($)':>10}"
        )
        width = 92 + (8 if show_trial else 0)

        print(f"\n{'='*width}")
        print(header)
        print(f"{'-'*width}")
        passed_count = 0
        total_tokens = 0
        total_cost = 0.0
        any_unknown_cost = False
        for entry in results:
            status = "PASS" if entry["passed"] else "FAIL"
            violation = entry["violation"] or "-"
            passed_at = entry["passed_at"]
            passed_at_str = (
                "initial" if passed_at == 0
                else f"repair#{passed_at}" if passed_at > 0
                else "-"
            )
            trial_str = f" {entry['trial']:>6}" if show_trial else ""
            total_tokens += entry.get("tokens", 0)
            total_cost += entry.get("cost_usd", 0.0)
            if not entry.get("cost_known", True):
                any_unknown_cost = True
            print(
                f"{entry['task_id']:<10}"
                + trial_str
                + f" {status:>6} {entry['repairs']:>8}"
                + f" {entry['tools']:>6}  {violation:<14} {passed_at_str:>8}"
                + f" {entry.get('tokens', 0):>10,} {entry.get('cost_usd', 0.0):>10.4f}"
            )
            if entry["passed"]:
                passed_count += 1
        print(f"{'-'*width}")
        note = "  (* some costs unknown — missing model pricing)" if any_unknown_cost else ""
        print(
            f"Total: {passed_count}/{len(results)} passed | "
            f"{total_tokens:,} tokens | ${total_cost:.4f}{note}"
        )

        # Per-task aggregation when trials > 1
        if show_trial:
            from collections import defaultdict
            task_results: dict[str, list[bool]] = defaultdict(list)
            for entry in results:
                task_results[entry["task_id"]].append(entry["passed"])

            print(f"\n{'='*width}")
            print("Per-task aggregation:")
            print(f"{'-'*width}")
            total_tasks_passed = 0
            for key, passes in task_results.items():
                n_pass = sum(passes)
                n_total = len(passes)
                rate = n_pass / n_total * 100
                print(f"  {key:<16} {n_pass}/{n_total} ({rate:.0f}%)")
                if n_pass > 0:
                    total_tasks_passed += 1
            print(f"{'-'*width}")
            all_pass = sum(sum(p) for p in task_results.values())
            all_total = sum(len(p) for p in task_results.values())
            print(
                f"Overall: {all_pass}/{all_total} runs passed "
                f"({all_pass/all_total*100:.1f}%), "
                f"{total_tasks_passed}/{len(task_results)} tasks with >=1 pass"
            )


if __name__ == "__main__":
    main()
