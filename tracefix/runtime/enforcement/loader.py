"""Loader for states.json format produced by the tla-verify-pluscal pipeline.

Normalizes the extracted state machine format into the IR format expected by
tracefix.runtime.enforcement.engine.run_ir().

Usage:
    from tracefix.runtime.enforcement.loader import load_task
    from tracefix.runtime.enforcement.engine import run_ir
    ir = load_task("workspace/claude46_exp2/3E")
    result = run_ir(ir, seed=42, timeout=10)
"""

import copy
import json
from pathlib import Path


def _wrap_list(val):
    """Wrap a scalar value in a list; keep lists as-is; return [] for None."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def normalize_extracted_states(ir: dict, extracted: dict) -> dict:
    """Merge ir.json topology with states.json state machines.

    Args:
        ir: Topology dict with agents, resources, channels (from ir.json).
        extracted: Extracted states dict with initial_states, states (from states.json).

    Returns:
        Complete IR dict compatible with tracefix.runtime.enforcement.engine.run_ir().
    """
    ir = copy.deepcopy(ir)
    extracted = copy.deepcopy(extracted)

    initial_states = extracted.get("initial_states", {})

    # Merge initial_state into each agent
    for agent in ir["agents"]:
        aid = agent["id"]
        if aid in initial_states:
            agent["initial_state"] = initial_states[aid]

    # Collect all agents that use __done__ so we can generate terminal states
    done_states_needed: dict[str, str] = {}  # agent_id → terminal state id

    # Normalize each state's actions
    normalized_states = []
    for state in extracted.get("states", []):
        agent_id = state["agent"]
        new_state = {"id": state["id"], "agent": agent_id, "actions": []}

        for action in state.get("actions", []):
            new_action = {}

            # next_state → target, handle __done__
            target = action.get("next_state", action.get("target"))
            if target == "__done__":
                terminal_id = f"{agent_id}__done__"
                done_states_needed[agent_id] = terminal_id
                new_action["target"] = terminal_id
            else:
                new_action["target"] = target

            # acquire/release: string → list
            acq = action.get("acquire")
            if acq is not None:
                new_action["acquire"] = _wrap_list(acq)

            rel = action.get("release")
            if rel is not None:
                new_action["release"] = _wrap_list(rel)

            # send/receive: single object → list
            send = action.get("send")
            if send is not None:
                new_action["send"] = _wrap_list(send)

            recv = action.get("receive")
            if recv is not None:
                new_action["receive"] = _wrap_list(recv)

            # guard/increment: pass through as-is
            if "guard" in action:
                new_action["guard"] = action["guard"]
            if "increment" in action:
                new_action["increment"] = action["increment"]

            new_state["actions"].append(new_action)

        normalized_states.append(new_state)

    # Generate terminal states for __done__ targets
    for agent_id, terminal_id in done_states_needed.items():
        # Only add if not already present
        existing_ids = {s["id"] for s in normalized_states}
        if terminal_id not in existing_ids:
            normalized_states.append({
                "id": terminal_id,
                "agent": agent_id,
                "actions": [],
            })

    ir["states"] = normalized_states

    # Pass through local_variables for engine guard/increment support
    if "local_variables" in extracted:
        ir["local_variables"] = extracted["local_variables"]

    return ir


def load_task(task_dir: str | Path) -> dict:
    """Load a task from a directory containing ir.json and states.json.

    Args:
        task_dir: Path to directory with ir.json and states.json.

    Returns:
        Complete IR dict compatible with tracefix.runtime.enforcement.engine.run_ir().

    Raises:
        FileNotFoundError: If required files are missing.
    """
    task_dir = Path(task_dir)

    ir_path = task_dir / "ir.json"
    states_path = task_dir / "states.json"

    if not ir_path.exists():
        raise FileNotFoundError(f"Missing ir.json in {task_dir}")
    if not states_path.exists():
        raise FileNotFoundError(f"Missing states.json in {task_dir}")

    with open(ir_path) as f:
        ir = json.load(f)
    with open(states_path) as f:
        extracted = json.load(f)

    result = normalize_extracted_states(ir, extracted)

    # Load per-agent prompts from prompts/runtime_a/
    prompts_dir = task_dir / "prompts" / "runtime_a"
    if prompts_dir.is_dir():
        prompts: dict[str, str] = {}
        for agent in result["agents"]:
            prompt_path = prompts_dir / f"{agent['id']}.md"
            if prompt_path.exists():
                prompts[agent["id"]] = prompt_path.read_text()
        if prompts:
            result["prompts"] = prompts

    return result
