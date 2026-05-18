"""Persist tracefix.runtime.monitoring execution results to JSON.

Serializes RunResult, agent traces, protocol monitor trace,
state tracker violations, and sim events into a single
self-contained ``run_result.json`` file.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _serialize_tool_call(tc) -> dict:
    """Serialize a single ToolCall."""
    return {
        "round": tc.round,
        "tool_name": tc.tool_name,
        "arguments": tc.arguments,
        "result": tc.result,
        "elapsed": round(tc.elapsed, 3),
        "timestamp": tc.timestamp,
    }


def _serialize_agent_result(ar) -> dict:
    """Serialize a single AgentResult + its ToolCall trace."""
    d: dict[str, Any] = {
        "agent_id": ar.agent_id,
        "status": ar.status,
        "steps": ar.steps,
        "duration": round(ar.duration, 3),
    }
    if ar.error:
        d["error"] = ar.error
    in_tok = getattr(ar, "input_tokens", 0)
    out_tok = getattr(ar, "output_tokens", 0)
    if in_tok or out_tok:
        d["input_tokens"] = in_tok
        d["output_tokens"] = out_tok
    d["trace"] = [_serialize_tool_call(tc) for tc in ar.trace]
    return d


def build_run_result_data(
    run_result,
    *,
    task_id: str,
    model: str,
    timeout: float = 180.0,
    scenario: int | None = None,
    difficulty: int = 1,
    tool_time: float | None = None,
    seed: int | None = None,
    monitor_trace: list | None = None,
    tracker_states: dict | None = None,
    tracker_violations: list | None = None,
    sim: Any = None,
) -> dict:
    """Assemble all execution data into a JSON-serializable dict."""
    meta: dict[str, Any] = {
        "task_id": task_id,
        "model": model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "timeout": timeout,
        "difficulty": difficulty,
    }
    if scenario is not None:
        meta["scenario"] = scenario
    if tool_time is not None:
        meta["tool_time"] = tool_time
    if seed is not None:
        meta["seed"] = seed
    total_in = sum(getattr(ar, "input_tokens", 0) for ar in run_result.agent_results)
    total_out = sum(getattr(ar, "output_tokens", 0) for ar in run_result.agent_results)
    result_block: dict[str, Any] = {
        "success": run_result.success,
        "duration": round(run_result.duration, 3),
    }
    if total_in or total_out:
        from tracefix.runtime.monitoring.cost import estimate_cost
        cost = estimate_cost(model, total_in, total_out)
        result_block["tokens"] = {"input": total_in, "output": total_out}
        if cost is not None:
            result_block["cost_usd"] = round(cost, 6)
    data: dict[str, Any] = {
        "meta": meta,
        "result": result_block,
        "agents": [_serialize_agent_result(ar) for ar in run_result.agent_results],
    }

    if run_result.error:
        data["result"]["error"] = run_result.error

    # Protocol monitor trace
    if monitor_trace:
        data["protocol_monitor"] = {
            "trace": [
                {
                    "agent": entry.agent,
                    "operation": entry.operation,
                    "target": entry.target,
                    **({"label": entry.label} if entry.label else {}),
                }
                for entry in monitor_trace
            ],
        }

    # State tracker
    if tracker_states is not None or tracker_violations:
        st: dict[str, Any] = {}
        if tracker_states is not None:
            st["final_states"] = tracker_states
        if tracker_violations:
            st["violations"] = [
                {
                    "agent": v.agent,
                    "current_state": v.current_state,
                    "operation": v.operation,
                    "args": v.args,
                    "valid_actions": v.valid_actions,
                    "timestamp": v.timestamp,
                }
                for v in tracker_violations
            ]
        data["state_tracker"] = st

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


def save_run_result(output_path: str | Path, run_result, **kwargs) -> Path:
    """Build and write run_result.json. Returns the output path."""
    path = Path(output_path)
    data = build_run_result_data(run_result, **kwargs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return path
