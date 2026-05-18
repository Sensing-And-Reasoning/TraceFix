"""Tool definitions wrapping v3 modules for the agentic verification loop.

Each tool is a function (ws: Workspace, **kwargs) -> str that returns a human-readable result.
Tools read/write files in the workspace directory.

Pipeline: IR (agents/resources/channels) -> PlusCal scaffold -> LLM fills process bodies -> verify_spec
"""

from __future__ import annotations

import json
import re as _re
from typing import Callable

from v3_agent_test.workspace import Workspace


# ---------------------------------------------------------------------------
# Tool schema definitions (provider-agnostic canonical format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    # -- Reasoning tools --
    {
        "name": "think",
        "description": (
            "Use this tool to think through your approach before acting. "
            "Call it to plan IR structure, analyze error traces, or reason about "
            "repair strategies. The content is recorded but has no side effects. "
            "You SHOULD call think() before writing ir.json and before each repair."
        ),
        "parameters": {
            "type": "object",
            "required": ["thoughts"],
            "properties": {
                "thoughts": {
                    "type": "string",
                    "description": "Your reasoning, analysis, or plan.",
                },
            },
        },
    },
    # -- File tools --
    {
        "name": "write_file",
        "description": (
            "Write content to a file in the workspace. Use this to create or update "
            "any file: ir.json, Protocol.tla, notes/*.md, etc. When ir.json is written, "
            "downstream files (Protocol.tla, Protocol.cfg, tlc_output.log, tlc_error.md) "
            "are automatically cleared."
        ),
        "parameters": {
            "type": "object",
            "required": ["path", "content"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Relative path within the workspace, e.g. 'ir.json', "
                        "'Protocol.tla', 'notes/analysis.md'."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "File content to write.",
                },
            },
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read a file from the workspace. Returns the file content or an error "
            "if the file does not exist. Use to inspect ir.json, Protocol.tla, "
            "tlc_output.log, tlc_error.md, notes/*.md, etc."
        ),
        "parameters": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path within the workspace.",
                },
            },
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Make a precise edit to a file by replacing an exact string match. "
            "Provide the old_string to find and new_string to replace it with. "
            "The old_string must appear exactly once in the file (unless replace_all is true). "
            "Use this for surgical edits to Protocol.tla process bodies or ir.json. "
            "When editing ir.json, downstream files are auto-cleared."
        ),
        "parameters": {
            "type": "object",
            "required": ["path", "old_string", "new_string"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path within the workspace.",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text to find and replace. Must match exactly (including whitespace).",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement text.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences instead of requiring uniqueness (default false).",
                    "default": False,
                },
            },
        },
    },
    {
        "name": "list_files",
        "description": "List all files in the workspace directory.",
        "parameters": {"type": "object", "properties": {}},
    },
    # -- Verification tools --
    {
        "name": "validate_ir",
        "description": (
            "Validate ir.json against the v3 JSON schema and semantic rules. "
            "Checks agents, resources, and channels (not states — those are PlusCal). "
            "Returns 'Valid' or a list of errors."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "compile_scaffold",
        "description": (
            "Generate the PlusCal scaffold from ir.json. Reads agents/resources/channels "
            "and writes Protocol.tla (with PlusCal boilerplate, macros, and process stubs) "
            "plus Protocol.cfg. You then fill in the process bodies with PlusCal code "
            "using edit_file, then call verify_spec to translate and model-check."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "verify_spec",
        "description": (
            "One-step verification: validate IR, read Protocol.tla, translate PlusCal "
            "(pcal.trans), and run TLC model checker. Returns PASS/FAIL with error details "
            "inline. If PlusCal has syntax errors, returns the pcal.trans error with line "
            "numbers. If TLC finds violations, returns the error trace. This is the "
            "preferred verification tool — use after filling in PlusCal process bodies."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "timeout": {
                    "type": "integer",
                    "description": "TLC timeout in seconds (default 120).",
                    "default": 120,
                },
            },
        },
    },
    {
        "name": "extract_states",
        "description": (
            "Extract per-agent state machine from the verified Protocol. "
            "Reads Protocol_translated.tla and ir.json, writes states.json. "
            "Call after verify_spec returns PASS. Required before Phase 4 prompt generation."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    # -- Workflow tools --
    {
        "name": "load_benchmark",
        "description": (
            "Load a benchmark task and write task.md, tools.json, and metadata.json "
            "to the workspace. task.md is the task description; tools.json is the "
            "per-agent domain tool schemas (filter by agent_ids); metadata.json is "
            "the canonical source for agent/resource IDs — IR names MUST match it.\n"
            "Task IDs like '1E', '2M', '5H' "
            "(33 coordination tasks across 11 scenarios, 3 difficulties)."
        ),
        "parameters": {
            "type": "object",
            "required": ["task_id"],
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": (
                        "Benchmark task ID: '1E', '2M', '5H', '10H', etc. "
                        "Format: {scenario}{difficulty} where scenario=1-11, difficulty=E/M/H."
                    ),
                },
            },
        },
    },
]


# ---------------------------------------------------------------------------
# File tools
# ---------------------------------------------------------------------------


def write_file(ws: Workspace, *, path: str, content: str) -> str:
    """Write content to a file in the workspace."""
    try:
        ws.write_file(path, content)
    except ValueError as e:
        return f"ERROR: {e}"

    # Provide summary for ir.json
    if path == "ir.json":
        ir_data = ws.read_ir()
        if ir_data is None:
            return (
                "Wrote ir.json but it is not valid JSON. "
                "Fix the content and write again."
            )
        agents = ir_data.get("agents", [])
        resources = ir_data.get("resources", [])
        channels = ir_data.get("channels", [])
        return (
            f"Wrote ir.json. Downstream files cleared.\n"
            f"  Agents: {len(agents)} ({', '.join(a.get('id', '?') for a in agents)})\n"
            f"  Resources: {len(resources)}"
            + (
                f" ({', '.join(r.get('id', '?') + ' (' + r.get('type', '?') + ')' for r in resources)})"
                if resources
                else ""
            )
            + f"\n  Channels: {len(channels)}"
            + (
                f" ({', '.join(c.get('id', '?') for c in channels)})"
                if channels
                else ""
            )
        )

    return f"Wrote {path} ({len(content)} bytes)."


def edit_file(
    ws: Workspace, *, path: str, old_string: str, new_string: str, replace_all: bool = False
) -> str:
    """Replace an exact string match in a workspace file."""
    try:
        content = ws.read_file(path)
    except ValueError as e:
        return f"ERROR: {e}"

    if content is None:
        return f"ERROR: File not found: {path}"

    if old_string == new_string:
        return "ERROR: old_string and new_string are identical."

    count = content.count(old_string)
    if count == 0:
        return (
            f"ERROR: old_string not found in {path}. "
            f"Make sure it matches exactly (including whitespace and newlines)."
        )

    if count > 1 and not replace_all:
        return (
            f"ERROR: old_string appears {count} times in {path}. "
            f"Provide more context to make it unique, or set replace_all=true."
        )

    new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)

    try:
        ws.write_file(path, new_content)
    except ValueError as e:
        return f"ERROR: {e}"

    replacements = count if replace_all else 1
    result = f"Edited {path}: replaced {replacements} occurrence(s)."

    # If ir.json was edited, show summary
    if path == "ir.json":
        ir_data = ws.read_ir()
        if ir_data is None:
            result += "\nWARNING: ir.json is no longer valid JSON after edit."
        else:
            agents = ir_data.get("agents", [])
            channels = ir_data.get("channels", [])
            result += f" Downstream files cleared. ({len(agents)} agents, {len(channels)} channels)"

    return result


def read_file(ws: Workspace, *, path: str) -> str:
    """Read a file from the workspace."""
    try:
        content = ws.read_file(path)
    except ValueError as e:
        return f"ERROR: {e}"

    if content is None:
        return f"File not found: {path}"
    return content


def list_files(ws: Workspace) -> str:
    """List all files in the workspace."""
    files = ws.list_files()
    if not files:
        return "Workspace is empty."
    return "\n".join(files)


def think(ws: Workspace, *, thoughts: str) -> str:
    """No-op reasoning tool. Records thoughts in conversation history."""
    return "OK"


# ---------------------------------------------------------------------------
# Verification tools
# ---------------------------------------------------------------------------


def validate_ir(ws: Workspace) -> str:
    """Validate ir.json against schema + semantic rules."""
    from v3_agent_test.pipeline.validator import validate_ir as _validate_ir

    ir_data = ws.read_ir()
    if ir_data is None:
        return "ERROR: No valid ir.json in workspace. Write ir.json first."

    result = _validate_ir(ir_data)

    # Record structured result
    ws.result.ir_valid = result.valid
    ws.result.ir_errors = list(result.errors)
    # Update latest repair attempt if one exists
    if ws.result.repairs:
        ws.result.repairs[-1].ir_valid = result.valid

    if result.valid:
        return "Valid. IR passes schema and semantic validation."
    else:
        errors = "\n".join(f"  - {e}" for e in result.errors)
        return f"INVALID. {len(result.errors)} error(s):\n{errors}"


def compile_scaffold(ws: Workspace) -> str:
    """Generate PlusCal scaffold from ir.json."""
    from v3_agent_test.pipeline.pluscal_generator import (
        generate_pluscal_scaffold,
        generate_tlc_config,
    )

    ir_data = ws.read_ir()
    if ir_data is None:
        return "ERROR: No valid ir.json in workspace. Write ir.json first."

    try:
        tla_scaffold = generate_pluscal_scaffold(ir_data)
        tlc_config = generate_tlc_config(ir_data)
    except Exception as e:
        return f"ERROR: Scaffold generation failed \u2014 {type(e).__name__}: {e}"

    ws.write_file("Protocol.tla", tla_scaffold)
    ws.write_file("Protocol.cfg", tlc_config)

    lines = tla_scaffold.split("\n")
    return (
        f"OK. Wrote Protocol.tla ({len(lines)} lines) + Protocol.cfg.\n"
        f"The process bodies contain 'skip' placeholders.\n"
        f"Use edit_file to replace each process body with PlusCal code, "
        f"then call verify_spec to translate and model-check."
    )


def verify_spec(ws: Workspace, *, timeout: int = 120) -> str:
    """One-step verification: validate IR, translate PlusCal, run TLC."""
    from v3_agent_test.pipeline.validator import validate_ir as _validate_ir
    from v3_agent_test.pipeline.pluscal_compiler import translate_pluscal
    from v3_agent_test.pipeline.tlc_runner import run_tlc as _run_tlc
    from v3_agent_test.pipeline.error_formatter import format_tlc_error
    from v3_agent_test.pipeline.trace_parser import parse_trace
    from v3_agent_test.workspace import RepairAttempt

    # Track repair attempts: if previous TLC failed, this is a repair
    if ws.result.tlc_status == "fail":
        # Circuit breaker: abort if same violation persisted across 3 repairs
        if len(ws.result.repairs) >= 3:
            recent = [r.new_violation_type for r in ws.result.repairs[-3:]]
            if recent[0] and recent[0] == recent[1] == recent[2]:
                return (
                    f"CIRCUIT BREAKER: Same violation type ({recent[0]}) "
                    f"persisted across 3 consecutive repair attempts. "
                    f"The underlying issue is likely beyond automated repair. "
                    f"Consider redesigning the protocol or simplifying the IR."
                )

        ws.repair_count += 1
        ws.result.repairs.append(RepairAttempt(
            attempt=ws.repair_count,
            success=True,  # updated below if validation fails
            violation_type=ws.result.tlc_violation_type,
        ))

    # Step 1: Read + validate IR (agents/resources/channels)
    ir_data = ws.read_ir()
    if ir_data is None:
        return "ERROR: No valid ir.json in workspace. Write ir.json first."

    val_result = _validate_ir(ir_data)
    ws.result.ir_valid = val_result.valid
    ws.result.ir_errors = list(val_result.errors)
    if ws.result.repairs:
        ws.result.repairs[-1].ir_valid = val_result.valid

    if not val_result.valid:
        if ws.result.repairs:
            ws.result.repairs[-1].success = False
        errors = "\n".join(f"  - {e}" for e in val_result.errors)
        return f"INVALID IR. {len(val_result.errors)} error(s):\n{errors}"

    # Step 2: Read Protocol.tla from workspace
    tla_content = ws.read_tla()
    if tla_content is None:
        return (
            "ERROR: No Protocol.tla in workspace. "
            "Call compile_scaffold first, then fill in PlusCal process bodies."
        )

    cfg_content = ws.read_cfg() or ""

    # Step 3: Translate PlusCal -> TLA+
    pcal_result = translate_pluscal(tla_content, cfg_content)

    if not pcal_result.success:
        ws.result.tlc_status = "fail"
        ws.result.tlc_violation_type = "pcal_error"
        if ws.result.repairs:
            ws.result.repairs[-1].tlc_passed = False
            ws.result.repairs[-1].new_violation_type = "pcal_error"

        ws.write_file("tlc_error.md", f"# PlusCal Translation Error\n\n{pcal_result.error_message}")
        ws._backup_protocol_attempt()
        return (
            f"FAIL \u2014 PlusCal syntax error:\n{pcal_result.error_message}"
        )

    # Save translated TLA+ for extract_states (Phase 4)
    ws.write_file("Protocol_translated.tla", pcal_result.translated_tla)

    # Step 4: Run TLC on translated spec
    tlc_result = _run_tlc(pcal_result.translated_tla, cfg_content, timeout=timeout)
    ws.write_file("tlc_output.log", tlc_result.raw_output)

    ws.result.tla_compiled = True
    ws.result.tla_lines = len(pcal_result.translated_tla.split("\n"))

    stats = tlc_result.stats
    ws.result.tlc_states_generated = stats.get("states_generated", 0)
    ws.result.tlc_distinct_states = stats.get("distinct_states", 0)
    ws.result.tlc_elapsed_seconds = stats.get("elapsed_seconds", 0.0)
    ws.result.tlc_violation_type = tlc_result.violation_type or ""

    if tlc_result.success:
        ws.result.tlc_status = "pass"
        ws.result.final_passed = True
        ws.result.passed_at_repair = len(ws.result.repairs)
        if ws.result.repairs:
            ws.result.repairs[-1].tlc_passed = True
        error_path = ws.path("tlc_error.md")
        if error_path.exists():
            error_path.unlink()
        return (
            f"PASS. PlusCal translated ({ws.result.tla_lines} lines TLA+). "
            f"TLC: {stats.get('states_generated', '?')} states generated, "
            f"{stats.get('distinct_states', '?')} distinct. "
            f"Time: {stats.get('elapsed_seconds', '?')}s."
        )

    # Failed
    ws.result.tlc_status = "fail"
    if ws.result.repairs:
        ws.result.repairs[-1].tlc_passed = False
        ws.result.repairs[-1].new_violation_type = tlc_result.violation_type or ""

    trace = parse_trace(tlc_result.raw_output)
    error_formatted = format_tlc_error(tlc_result, trace)
    ws.write_file("tlc_error.md", error_formatted)
    ws._backup_protocol_attempt()

    header = (
        f"FAIL \u2014 {tlc_result.violation_type or 'unknown'} violation. "
        f"PlusCal translated ({ws.result.tla_lines} lines).\n\n"
    )
    max_error_chars = 1800 - len(header)
    if len(error_formatted) > max_error_chars:
        error_inline = error_formatted[:max_error_chars] + "\n... (truncated, see tlc_error.md for full trace)"
    else:
        error_inline = error_formatted
    return header + error_inline


# ---------------------------------------------------------------------------
# State extraction tools
# ---------------------------------------------------------------------------


def extract_states(ws: Workspace) -> str:
    """Extract per-agent state machine from verified Protocol_translated.tla."""
    import json as _json
    from v3_agent_test.pipeline.pluscal_parser import (
        parse_pluscal,
        lint_adjacent_acquire_release,
    )

    translated = ws.read_file("Protocol_translated.tla")
    if translated is None:
        return "ERROR: Protocol_translated.tla not found. Call verify_spec first (must PASS)."

    ir_data = ws.read_ir()
    if ir_data is None:
        return "ERROR: No valid ir.json in workspace."

    result = parse_pluscal(translated, ir_data)

    # Annotate tool_hints (same logic as cli.py _annotate_tool_hints)
    for state in result.states:
        actions = state.get("actions", [])
        if len(actions) <= 1:
            continue
        has_recv = [bool(a.get("receive")) for a in actions]
        if all(has_recv):
            state["tool_hint"] = "receive_any"
        elif any(has_recv):
            state["tool_hint"] = "poll_channels"

    lint_warnings = lint_adjacent_acquire_release(result.states)

    out_data = {"states": result.states, "initial_states": result.initial_states}
    if result.local_variables:
        out_data["local_variables"] = result.local_variables
    ws.write_file("states.json", _json.dumps(out_data, indent=2))

    n_actions = sum(len(s.get("actions", [])) for s in result.states)
    n_terminal = sum(1 for s in result.states if not s.get("actions"))
    parts = [f"OK — wrote states.json. {len(result.states)} states, {n_actions} actions, {n_terminal} terminal."]
    if result.errors:
        parts.append(f"WARNING: {len(result.errors)} parse error(s):")
        parts.extend(f"  - {e}" for e in result.errors)
    if lint_warnings:
        parts.append(f"LINT: {len(lint_warnings)} work-state warning(s):")
        parts.extend(f"  - {w}" for w in lint_warnings)
    parts.append("Next: read states.json, then generate per-agent prompts (Phase 4).")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Workflow tools
# ---------------------------------------------------------------------------


def load_benchmark(ws: Workspace, *, task_id: str) -> str:
    """Load a benchmark task by ID.

    Copies description.md -> task.md, and tools.json/metadata.json verbatim
    (preserving skill-compatible naming). tools.json and metadata.json must be
    referenced by those exact names in later phases.
    """
    from pathlib import Path
    from benchmark.loader import load_task

    try:
        task = load_task(task_id)
    except ValueError as e:
        return f"ERROR: {e}"

    # Write task description to workspace
    ws.write_file("task.md", task.description)

    desc_dir = Path(__file__).resolve().parent.parent / "benchmark" / "descriptions" / task.task_id
    extras: list[str] = []

    # Copy tools.json (per-agent domain tool schemas)
    tools_path = desc_dir / "tools.json"
    if tools_path.exists():
        tools_content = tools_path.read_text(encoding="utf-8")
        ws.write_file("tools.json", tools_content)
        try:
            tools_data = json.loads(tools_content)
            extras.append(f"tools.json: {len(tools_data)} domain tool schema(s)")
        except json.JSONDecodeError:
            extras.append("tools.json: copied (unparsed)")

    # Copy metadata.json (canonical agent/resource IDs)
    metadata_path = desc_dir / "metadata.json"
    if metadata_path.exists():
        metadata_content = metadata_path.read_text(encoding="utf-8")
        ws.write_file("metadata.json", metadata_content)
        extras.append("metadata.json: canonical naming source")

    extras_msg = "\n  " + "\n  ".join(extras) if extras else ""

    return (
        f"Loaded task: {task.task_name}\n"
        f"  ID: {task.task_id}\n"
        f"  Scenario: {task.scenario}, Difficulty: {task.difficulty}\n"
        f"  Description written to task.md ({len(task.description)} chars)."
        + extras_msg
    )


# ---------------------------------------------------------------------------
# Tool registry: maps tool name -> callable
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, Callable[..., str]] = {
    "think": think,
    "write_file": write_file,
    "edit_file": edit_file,
    "read_file": read_file,
    "list_files": list_files,
    "validate_ir": validate_ir,
    "compile_scaffold": compile_scaffold,
    "verify_spec": verify_spec,
    "extract_states": extract_states,
    "load_benchmark": load_benchmark,
}
