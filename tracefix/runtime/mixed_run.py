"""Mixed-harness demo: prove tracefix is a harness-agnostic coordination layer.

Run ONE verified workspace with some agents driven by **opencode** (separate
processes) and the rest by the **Claude Agent SDK** (in-process), all coordinating
through ONE authoritative ``CoordinationService`` (the same verified
``CoordinationContext`` + monitor + tracker + correction). Channels that cross the
opencode/SDK boundary force the two harnesses to coordinate with each other —
identical semantics, two completely different agent runtimes.

    python -m tracefix.runtime.mixed_run \
        --task mas_research --workspace workspace/mas_research \
        --opencode-agents RESEARCHER_FM,RESEARCHER_RT,PLOTTER \
        --sdk-agents RESEARCHER_EVAL,CHECKER,APPROVER \
        --opencode-model openai/gpt-5.4-mini

Both orchestrators are pointed at the driver's service via ``coord_url`` (so they
do NOT start their own), at one shared snapshot ``output/`` via ``output_dir`` (so
their files land together), and each runs only its assigned ``agents`` subset.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from tracefix.runtime.monitoring.coord import CoordinationContext
from tracefix.runtime.monitoring.monitor import ProtocolMonitor
from tracefix.runtime.monitoring.state_tracker import StateTracker
from tracefix.runtime.coordination.service import CoordinationService
from tracefix.runtime.workspace_layout import (
    spec_path, snapshot_run_workspace, new_run_stamp,
)
from tracefix.runtime.opencode_adapter.orchestrator import OpencodeOrchestrator
from tracefix.runtime.sdk_adapter.orchestrator import SdkOrchestrator


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def _split(csv: str | None) -> list[str]:
    return [a.strip() for a in (csv or "").split(",") if a.strip()]


def validate_split(all_ids, opencode_agents, sdk_agents) -> str | None:
    """Error string if the opencode/sdk split doesn't cover every IR agent exactly
    once, else None. A bad split silently STALLS the protocol (an agent that never
    runs is never sent to / received from), so reject it loudly up front.
    """
    assigned = list(opencode_agents) + list(sdk_agents)
    dupes = sorted({a for a in assigned if assigned.count(a) > 1})
    missing = [a for a in all_ids if a not in assigned]
    unknown = [a for a in assigned if a not in all_ids]
    if dupes or missing or unknown:
        return (f"agent split invalid: duplicates={dupes} missing={missing} "
                f"unknown={unknown}; IR agents = {list(all_ids)}")
    return None


async def mixed_run(
    task_id: str,
    workspace: Path | str,
    *,
    opencode_agents: list[str],
    sdk_agents: list[str],
    opencode_model: str | None = None,
    sdk_model: str | None = None,
    opencode_cmd: list[str] | None = None,
    builtins: list[str] | None = None,
    host: str = "127.0.0.1",
    port: int = 8780,
    start_stagger: float = 8.0,
    opencode_timeout: float = 600.0,
    sdk_timeout: float = 400.0,
    verbose: bool = False,
) -> dict:
    workspace = Path(workspace)
    ir = _load_json(spec_path(workspace, "ir.json"))
    all_ids = [a["id"] for a in ir["agents"]]

    # Validate the split covers every agent exactly once — otherwise the protocol
    # stalls on an agent that never runs (or double-runs).
    err = validate_split(all_ids, opencode_agents, sdk_agents)
    if err:
        raise SystemExit(err)

    # ONE authoritative coordination service (monitor + tracker + correction).
    monitor = ProtocolMonitor(ir)
    states_path = spec_path(workspace, "states.json")
    tracker = StateTracker(_load_json(states_path)) if states_path.exists() else None
    coord = CoordinationContext(ir, monitor, tracker=tracker, correction=True)
    service = CoordinationService(coord, host=host, port=port, verbose=verbose)
    await service.start()
    coord_url = f"http://{host}:{port}"

    # ONE shared snapshot workspace; both harnesses write into its output/.
    snapshot = snapshot_run_workspace(workspace, new_run_stamp())
    shared_out = snapshot / "output"
    print(f"[mixed] coordination service on {coord_url}")
    print(f"[mixed] run snapshot → {snapshot}")
    print(f"[mixed] opencode agents: {opencode_agents}")
    print(f"[mixed] sdk agents:      {sdk_agents}")

    oc = OpencodeOrchestrator(
        task_id, workspace, model=opencode_model, opencode_cmd=opencode_cmd,
        coord_url=coord_url, agents=opencode_agents, output_dir=shared_out,
        start_stagger=start_stagger, timeout=opencode_timeout, verbose=verbose)
    sk = SdkOrchestrator(
        task_id, workspace, model=sdk_model, builtins=builtins,
        coord_url=coord_url, agents=sdk_agents, output_dir=shared_out,
        verbose=verbose)

    start = time.time()
    try:
        oc_res, sk_res = await asyncio.gather(
            oc.run(), sk.run(timeout=sdk_timeout), return_exceptions=True)
    finally:
        await service.stop()
    duration = time.time() - start

    # The driver's in-process tracker is authoritative for the whole run.
    violations = []
    final_states = {}
    if tracker is not None:
        for v in tracker.violations:
            violations.append({
                "agent": getattr(v, "agent", None),
                "state": getattr(v, "current_state", None),
                "operation": getattr(v, "operation", None),
                "args": getattr(v, "args", None)})
        final_states = dict(tracker.current_states)

    return {
        "duration": duration,
        "snapshot": str(snapshot),
        "opencode": oc_res,
        "sdk": sk_res,
        "violations": violations,
        "final_states": final_states,
        "agent_ids": all_ids,
    }


def _status_line(label: str, res) -> list[str]:
    if isinstance(res, BaseException):
        return [f"  [{label}] ERROR: {type(res).__name__}: {res}"]
    lines = []
    # opencode result.agent_results is list[dict]; sdk result.agent_results is list[AgentResult]
    for r in getattr(res, "agent_results", []) or []:
        if isinstance(r, dict):
            aid, st, nc = r.get("agent_id"), r.get("status"), len(r.get("tool_calls", []))
        else:
            aid, st, nc = r.agent_id, r.status, r.steps
        lines.append(f"  [{label}] {aid}: {nc} tool calls, {st}")
    return lines


def main() -> None:
    p = argparse.ArgumentParser(
        prog="python -m tracefix.runtime.mixed_run",
        description="Run one verified workspace across opencode + Claude-SDK agents "
                    "on a single coordination layer (harness-agnostic proof).")
    p.add_argument("--task", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--opencode-agents", required=True,
                   help="Comma-separated agent ids to run via opencode")
    p.add_argument("--sdk-agents", required=True,
                   help="Comma-separated agent ids to run via the Claude SDK")
    p.add_argument("--opencode-model", default=None, help="e.g. openai/gpt-5.4-mini")
    p.add_argument("--sdk-model", default=None, help="SDK model (default: CLI default)")
    p.add_argument("--opencode-bin", default="opencode")
    p.add_argument("--builtins", default="Read,Write,Edit",
                   help="SDK built-in tools for the sdk agents")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8780)
    p.add_argument("--start-stagger", type=float, default=8.0)
    p.add_argument("--opencode-timeout", type=float, default=600.0)
    p.add_argument("--sdk-timeout", type=float, default=400.0)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    import shlex
    result = asyncio.run(mixed_run(
        args.task, args.workspace,
        opencode_agents=_split(args.opencode_agents),
        sdk_agents=_split(args.sdk_agents),
        opencode_model=args.opencode_model, sdk_model=args.sdk_model,
        opencode_cmd=shlex.split(args.opencode_bin),
        builtins=[b.strip() for b in args.builtins.split(",") if b.strip()],
        host=args.host, port=args.port, start_stagger=args.start_stagger,
        opencode_timeout=args.opencode_timeout, sdk_timeout=args.sdk_timeout,
        verbose=args.verbose))

    print("\n=== Mixed-Harness Run ===")
    print(f"duration: {result['duration']:.1f}s")
    print(f"snapshot: {result['snapshot']}  (shared output/ from BOTH harnesses)")
    for line in _status_line("opencode", result["opencode"]):
        print(line)
    for line in _status_line("sdk", result["sdk"]):
        print(line)
    print("\n=== Coordination (one shared monitor over both harnesses) ===")
    if result["violations"]:
        print(f"  state-machine violations: {len(result['violations'])}")
        for v in result["violations"][:10]:
            print(f"    ⚠ {v.get('agent')} @ {v.get('state')}: "
                  f"{v.get('operation')}({v.get('args')})")
    else:
        print("  clean — no protocol violations across either harness")
    done = sum(1 for s in result["final_states"].values() if str(s).endswith("_done"))
    print(f"  agents at a done state: {done}/{len(result['agent_ids'])}")

    # success = every agent completed cleanly across both harnesses
    def _all_completed(res) -> bool:
        if isinstance(res, BaseException):
            return False
        rs = getattr(res, "agent_results", []) or []
        def _st(r):
            return r.get("status") if isinstance(r, dict) else r.status
        return bool(rs) and all(_st(r) == "completed" for r in rs)

    ok = (_all_completed(result["opencode"]) and _all_completed(result["sdk"])
          and not result["violations"])
    print(f"\n{'SUCCESS' if ok else 'INCOMPLETE'} — mixed harness, one coordination layer")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
