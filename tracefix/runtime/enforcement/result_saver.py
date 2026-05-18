"""Persist tracefix.runtime.enforcement execution results to JSON.

Serializes RunResult and TraceEvent data into a single
``run_result.json`` file, structured to align with tracefix.runtime.monitoring's format
but adapted for tracefix.runtime.enforcement's enforcement-architecture trace model.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tracefix.runtime.enforcement.engine import RunResult


def _serialize_trace_event(ev) -> dict:
    """Serialize a single TraceEvent."""
    d: dict[str, Any] = {
        "step": ev.step,
        "timestamp": round(ev.timestamp, 3),
        "agent": ev.agent,
        "from_state": ev.from_state,
        "to_state": ev.to_state,
    }
    if ev.guards:
        d["guards"] = ev.guards
    if ev.effects:
        d["effects"] = ev.effects
    if ev.tool_calls:
        d["tool_calls"] = ev.tool_calls
    return d


def _aggregate_agents(run_result: RunResult) -> dict[str, dict]:
    """Aggregate per-agent statistics from the trace."""
    agents: dict[str, dict[str, Any]] = {}
    for ev in run_result.trace:
        if ev.agent not in agents:
            agents[ev.agent] = {"steps": 0, "tool_calls": 0}
        agents[ev.agent]["steps"] += 1
        agents[ev.agent]["tool_calls"] += len(ev.tool_calls)

    # Add final states
    for aid, state in run_result.final_states.items():
        if aid not in agents:
            agents[aid] = {"steps": 0, "tool_calls": 0}
        agents[aid]["final_state"] = state

    return agents


def build_run_result_data(
    run_result: RunResult,
    *,
    task_id: str,
    model: str,
    timeout: float = 5.0,
    seed: int | None = None,
    sim: Any = None,
    difficulty: int = 1,
    scenario: int | None = None,
    tool_time: float | None = None,
) -> dict:
    """Assemble all execution data into a JSON-serializable dict."""
    meta: dict[str, Any] = {
        "task_id": task_id,
        "runtime": "A",
        "model": model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "timeout": timeout,
    }
    if seed is not None:
        meta["seed"] = seed
    if scenario is not None:
        meta["scenario"] = scenario
    else:
        meta["difficulty"] = difficulty
    if tool_time is not None:
        meta["tool_time"] = tool_time

    result_data: dict[str, Any] = {
        "success": run_result.success,
        "duration": round(run_result.duration, 3),
        "steps": run_result.steps,
    }
    if run_result.error:
        result_data["error"] = run_result.error
    if run_result.final_states:
        result_data["final_states"] = run_result.final_states
    if run_result.final_locks:
        result_data["final_locks"] = run_result.final_locks
    if run_result.final_channels:
        result_data["final_channels"] = run_result.final_channels
    if run_result.final_counters:
        result_data["final_counters"] = run_result.final_counters

    data: dict[str, Any] = {
        "meta": meta,
        "result": result_data,
        "trace": [_serialize_trace_event(ev) for ev in run_result.trace],
        "agents": _aggregate_agents(run_result),
    }

    # Sim data
    if sim is not None:
        sim_data: dict[str, Any] = {"progress": sim.progress}
        if sim.violations:
            sim_data["violations"] = [
                {
                    "timestamp": v.timestamp,
                    "agent": v.agent,
                    "tool": v.tool,
                    "violation_type": v.violation_type,
                    "message": v.message,
                }
                for v in sim.violations
            ]
        if sim.events:
            sim_data["events"] = [
                {
                    "timestamp": ev.timestamp,
                    "agent": ev.agent,
                    "tool": ev.tool,
                    "args": ev.args,
                    "success": ev.success,
                    "result": ev.result,
                    "violations": [
                        {
                            "violation_type": v.violation_type,
                            "agent": v.agent,
                            "tool": v.tool,
                            "message": v.message,
                        }
                        for v in ev.violations
                    ],
                }
                for ev in sim.events
            ]
        data["sim"] = sim_data

    return data


def save_run_result(output_path: str | Path, run_result: RunResult, **kwargs) -> Path:
    """Build and write run_result.json. Returns the output path."""
    path = Path(output_path)
    data = build_run_result_data(run_result, **kwargs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return path
