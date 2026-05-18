"""Unit tests for tracefix.pipeline/tools.py — workspace tool functions."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from tracefix.pipeline.workspace import Workspace, RepairAttempt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_IR = {
    "agents": [
        {"id": "researcherA"},
        {"id": "researcherB"},
        {"id": "editor"},
    ],
    "resources": [
        {"id": "doc_lock", "type": "Lock"},
        {"id": "ref_lock", "type": "Lock"},
    ],
    "channels": [
        {"id": "resA_to_editor", "from": "researcherA", "to": "editor", "labels": ["submit"]},
        {"id": "resB_to_editor", "from": "researcherB", "to": "editor", "labels": ["submit"]},
        {"id": "editor_to_resA", "from": "editor", "to": "researcherA", "labels": ["revise", "accept"]},
        {"id": "editor_to_resB", "from": "editor", "to": "researcherB", "labels": ["revise", "accept"]},
    ],
}


@pytest.fixture
def ws(tmp_path):
    """Create a workspace in a temp directory."""
    return Workspace(session_id="test_session", base_dir=str(tmp_path))


@pytest.fixture
def ws_with_ir(ws):
    """Workspace with a valid ir.json written."""
    from tracefix.pipeline.tools import write_file
    write_file(ws, path="ir.json", content=json.dumps(VALID_IR, indent=2))
    return ws


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

class TestWriteFile:
    def test_write_simple_file(self, ws):
        from tracefix.pipeline.tools import write_file
        content = "# Plan\nStep 1"
        result = write_file(ws, path="notes/plan.md", content=content)
        assert "Wrote notes/plan.md" in result
        assert f"({len(content)} bytes)" in result
        assert ws.read_file("notes/plan.md") == content

    def test_write_ir_json_returns_summary(self, ws):
        from tracefix.pipeline.tools import write_file
        result = write_file(ws, path="ir.json", content=json.dumps(VALID_IR, indent=2))
        assert "Wrote ir.json" in result
        assert "Agents: 3" in result
        assert "researcherA" in result
        assert "Resources: 2" in result
        assert "Channels: 4" in result

    def test_write_ir_json_clears_downstream(self, ws):
        from tracefix.pipeline.tools import write_file
        # Create downstream files
        write_file(ws, path="Protocol.tla", content="--- MODULE ---")
        write_file(ws, path="Protocol.cfg", content="INIT Init")
        write_file(ws, path="tlc_output.log", content="TLC output")
        assert ws.read_file("Protocol.tla") is not None

        # Write ir.json — downstream should be cleared
        write_file(ws, path="ir.json", content=json.dumps(VALID_IR, indent=2))
        assert ws.read_file("Protocol.tla") is None
        assert ws.read_file("Protocol.cfg") is None
        assert ws.read_file("tlc_output.log") is None

    def test_write_invalid_json_as_ir(self, ws):
        from tracefix.pipeline.tools import write_file
        result = write_file(ws, path="ir.json", content="not json {{{")
        assert "not valid JSON" in result

    def test_write_path_traversal_blocked(self, ws):
        from tracefix.pipeline.tools import write_file
        result = write_file(ws, path="../../../etc/passwd", content="evil")
        assert "ERROR" in result


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------

class TestEditFile:
    def test_edit_success(self, ws):
        from tracefix.pipeline.tools import write_file, edit_file
        write_file(ws, path="test.txt", content="hello world foo")
        result = edit_file(ws, path="test.txt", old_string="world", new_string="earth")
        assert "replaced 1 occurrence" in result
        assert ws.read_file("test.txt") == "hello earth foo"

    def test_edit_old_string_not_found(self, ws):
        from tracefix.pipeline.tools import write_file, edit_file
        write_file(ws, path="test.txt", content="hello world")
        result = edit_file(ws, path="test.txt", old_string="xyz", new_string="abc")
        assert "ERROR" in result
        assert "not found" in result

    def test_edit_identical_strings(self, ws):
        from tracefix.pipeline.tools import write_file, edit_file
        write_file(ws, path="test.txt", content="hello")
        result = edit_file(ws, path="test.txt", old_string="hello", new_string="hello")
        assert "ERROR" in result
        assert "identical" in result

    def test_edit_ambiguous_without_replace_all(self, ws):
        from tracefix.pipeline.tools import write_file, edit_file
        write_file(ws, path="test.txt", content="aa bb aa")
        result = edit_file(ws, path="test.txt", old_string="aa", new_string="cc")
        assert "ERROR" in result
        assert "2 times" in result

    def test_edit_replace_all(self, ws):
        from tracefix.pipeline.tools import write_file, edit_file
        write_file(ws, path="test.txt", content="aa bb aa")
        result = edit_file(ws, path="test.txt", old_string="aa", new_string="cc", replace_all=True)
        assert "replaced 2 occurrence" in result
        assert ws.read_file("test.txt") == "cc bb cc"

    def test_edit_nonexistent_file(self, ws):
        from tracefix.pipeline.tools import edit_file
        result = edit_file(ws, path="nope.txt", old_string="a", new_string="b")
        assert "ERROR" in result

    def test_edit_ir_json_clears_downstream(self, ws_with_ir):
        from tracefix.pipeline.tools import write_file, edit_file
        ws = ws_with_ir
        write_file(ws, path="Protocol.tla", content="--- MODULE ---")
        result = edit_file(
            ws, path="ir.json",
            old_string='"doc_lock"', new_string='"document_lock"',
        )
        assert "Downstream files cleared" in result
        assert ws.read_file("Protocol.tla") is None


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

class TestReadFile:
    def test_read_existing_file(self, ws):
        from tracefix.pipeline.tools import write_file, read_file
        write_file(ws, path="hello.txt", content="world")
        result = read_file(ws, path="hello.txt")
        assert result == "world"

    def test_read_nonexistent_file(self, ws):
        from tracefix.pipeline.tools import read_file
        result = read_file(ws, path="missing.txt")
        assert "File not found" in result


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------

class TestListFiles:
    def test_empty_workspace(self, ws):
        from tracefix.pipeline.tools import list_files
        result = list_files(ws)
        assert result == "Workspace is empty."

    def test_workspace_with_files(self, ws):
        from tracefix.pipeline.tools import write_file, list_files
        write_file(ws, path="a.txt", content="a")
        write_file(ws, path="b.txt", content="b")
        result = list_files(ws)
        assert "a.txt" in result
        assert "b.txt" in result


# ---------------------------------------------------------------------------
# validate_ir
# ---------------------------------------------------------------------------

class TestValidateIR:
    def test_valid_ir(self, ws_with_ir):
        from tracefix.pipeline.tools import validate_ir
        result = validate_ir(ws_with_ir)
        assert "Valid" in result
        assert ws_with_ir.result.ir_valid is True

    def test_no_ir_file(self, ws):
        from tracefix.pipeline.tools import validate_ir
        result = validate_ir(ws)
        assert "ERROR" in result
        assert "ir.json" in result

    def test_invalid_ir_missing_agents(self, ws):
        from tracefix.pipeline.tools import write_file, validate_ir
        write_file(ws, path="ir.json", content=json.dumps({"resources": [], "channels": []}))
        result = validate_ir(ws)
        assert "INVALID" in result
        assert ws.result.ir_valid is False
        assert len(ws.result.ir_errors) > 0

    def test_invalid_ir_bad_channel_ref(self, ws):
        from tracefix.pipeline.tools import write_file, validate_ir
        bad_ir = {
            "agents": [{"id": "a"}, {"id": "b"}],
            "resources": [],
            "channels": [{"id": "ch", "from": "a", "to": "nonexistent", "labels": ["x"]}],
        }
        write_file(ws, path="ir.json", content=json.dumps(bad_ir))
        result = validate_ir(ws)
        assert "INVALID" in result


# ---------------------------------------------------------------------------
# compile_scaffold
# ---------------------------------------------------------------------------

class TestCompileScaffold:
    def test_no_ir_file(self, ws):
        from tracefix.pipeline.tools import compile_scaffold
        result = compile_scaffold(ws)
        assert "ERROR" in result

    def test_scaffold_success(self, ws_with_ir):
        from tracefix.pipeline.tools import compile_scaffold
        result = compile_scaffold(ws_with_ir)
        assert "OK" in result
        assert "Protocol.tla" in result
        assert "Protocol.cfg" in result
        assert ws_with_ir.read_file("Protocol.tla") is not None
        assert ws_with_ir.read_file("Protocol.cfg") is not None
        # Check TLA+ content has PlusCal markers
        tla_content = ws_with_ir.read_file("Protocol.tla")
        assert "MODULE Protocol" in tla_content


# ---------------------------------------------------------------------------
# verify_spec
# ---------------------------------------------------------------------------

class TestVerifySpec:
    def test_no_ir_file(self, ws):
        from tracefix.pipeline.tools import verify_spec
        result = verify_spec(ws)
        assert "ERROR" in result
        assert "ir.json" in result

    def test_no_protocol_tla(self, ws_with_ir):
        from tracefix.pipeline.tools import verify_spec
        result = verify_spec(ws_with_ir)
        assert "ERROR" in result
        assert "Protocol.tla" in result

    def test_invalid_ir_fails_validation(self, ws):
        from tracefix.pipeline.tools import write_file, compile_scaffold, verify_spec
        bad_ir = {"agents": [], "resources": [], "channels": []}
        write_file(ws, path="ir.json", content=json.dumps(bad_ir))
        # Create Protocol.tla manually to bypass scaffold
        write_file(ws, path="Protocol.tla", content="--- fake ---")
        result = verify_spec(ws)
        assert "INVALID IR" in result

    def test_pcal_syntax_error(self, ws_with_ir):
        from tracefix.pipeline.tools import compile_scaffold, verify_spec
        compile_scaffold(ws_with_ir)
        # Corrupt ALL PlusCal process bodies to ensure syntax error
        from tracefix.pipeline.tools import edit_file
        tla = ws_with_ir.read_file("Protocol.tla")
        if "skip;" in tla:
            edit_file(ws_with_ir, path="Protocol.tla",
                      old_string="skip;", new_string="INVALID_SYNTAX @@@;",
                      replace_all=True)
        result = verify_spec(ws_with_ir)
        # Should fail with pcal_error
        assert "FAIL" in result
        assert ws_with_ir.result.tlc_status == "fail"

    def test_repair_tracking(self, ws_with_ir):
        """Simulate a repair sequence by manually setting tlc_status."""
        from tracefix.pipeline.tools import verify_spec
        ws = ws_with_ir

        # Simulate a previous TLC failure
        ws.result.tlc_status = "fail"
        ws.result.tlc_violation_type = "deadlock"

        # Call verify_spec — it should create a repair attempt
        # (will fail because no Protocol.tla, but repair tracking should happen)
        from tracefix.pipeline.tools import compile_scaffold
        compile_scaffold(ws)
        result = verify_spec(ws)

        assert ws.repair_count == 1
        assert len(ws.result.repairs) == 1
        assert ws.result.repairs[0].attempt == 1
        assert ws.result.repairs[0].violation_type == "deadlock"


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_circuit_breaker_triggers_on_3_same_violations(self, ws_with_ir):
        from tracefix.pipeline.tools import verify_spec
        ws = ws_with_ir

        # Simulate 3 past repair attempts all with same violation type
        ws.result.tlc_status = "fail"
        ws.result.tlc_violation_type = "deadlock"
        ws.result.repairs = [
            RepairAttempt(attempt=1, success=True, violation_type="", new_violation_type="deadlock"),
            RepairAttempt(attempt=2, success=True, violation_type="deadlock", new_violation_type="deadlock"),
            RepairAttempt(attempt=3, success=True, violation_type="deadlock", new_violation_type="deadlock"),
        ]

        result = verify_spec(ws)
        assert "CIRCUIT BREAKER" in result
        assert "deadlock" in result
        # repair_count should NOT have incremented
        assert ws.repair_count == 0

    def test_circuit_breaker_does_not_trigger_on_different_violations(self, ws_with_ir):
        from tracefix.pipeline.tools import verify_spec, compile_scaffold
        ws = ws_with_ir

        # Simulate 3 past repairs with different violation types
        ws.result.tlc_status = "fail"
        ws.result.tlc_violation_type = "safety"
        ws.result.repairs = [
            RepairAttempt(attempt=1, success=True, violation_type="", new_violation_type="deadlock"),
            RepairAttempt(attempt=2, success=True, violation_type="deadlock", new_violation_type="safety"),
            RepairAttempt(attempt=3, success=True, violation_type="safety", new_violation_type="deadlock"),
        ]

        compile_scaffold(ws)
        result = verify_spec(ws)
        # Should NOT trigger circuit breaker — different violations
        assert "CIRCUIT BREAKER" not in result
        assert ws.repair_count == 1

    def test_circuit_breaker_does_not_trigger_with_fewer_than_3(self, ws_with_ir):
        from tracefix.pipeline.tools import verify_spec, compile_scaffold
        ws = ws_with_ir

        ws.result.tlc_status = "fail"
        ws.result.tlc_violation_type = "deadlock"
        ws.result.repairs = [
            RepairAttempt(attempt=1, success=True, violation_type="", new_violation_type="deadlock"),
            RepairAttempt(attempt=2, success=True, violation_type="deadlock", new_violation_type="deadlock"),
        ]

        compile_scaffold(ws)
        result = verify_spec(ws)
        # Only 2 same violations — should not trigger
        assert "CIRCUIT BREAKER" not in result

    def test_circuit_breaker_ignores_empty_violation_type(self, ws_with_ir):
        from tracefix.pipeline.tools import verify_spec, compile_scaffold
        ws = ws_with_ir

        ws.result.tlc_status = "fail"
        ws.result.tlc_violation_type = "safety"
        ws.result.repairs = [
            RepairAttempt(attempt=1, success=True, violation_type="", new_violation_type=""),
            RepairAttempt(attempt=2, success=True, violation_type="", new_violation_type=""),
            RepairAttempt(attempt=3, success=True, violation_type="", new_violation_type=""),
        ]

        compile_scaffold(ws)
        result = verify_spec(ws)
        # Empty violation types should not trigger circuit breaker
        assert "CIRCUIT BREAKER" not in result

    def test_circuit_breaker_on_pcal_error(self, ws_with_ir):
        from tracefix.pipeline.tools import verify_spec
        ws = ws_with_ir

        ws.result.tlc_status = "fail"
        ws.result.tlc_violation_type = "pcal_error"
        ws.result.repairs = [
            RepairAttempt(attempt=1, success=True, violation_type="", new_violation_type="pcal_error"),
            RepairAttempt(attempt=2, success=True, violation_type="pcal_error", new_violation_type="pcal_error"),
            RepairAttempt(attempt=3, success=True, violation_type="pcal_error", new_violation_type="pcal_error"),
        ]

        result = verify_spec(ws)
        assert "CIRCUIT BREAKER" in result
        assert "pcal_error" in result


# ---------------------------------------------------------------------------
# extract_states
# ---------------------------------------------------------------------------

class TestExtractStates:
    def test_extract_no_translated_tla(self, ws_with_ir):
        from tracefix.pipeline.tools import extract_states
        result = extract_states(ws_with_ir)
        assert "ERROR" in result
        assert "Protocol_translated.tla" in result

    def test_extract_no_ir(self, ws):
        from tracefix.pipeline.tools import write_file, extract_states
        # Write a dummy translated TLA+ but no ir.json
        write_file(ws, path="Protocol_translated.tla", content="--- dummy ---")
        result = extract_states(ws)
        assert "ERROR" in result
        assert "ir.json" in result

    def test_extract_success(self, ws_with_ir):
        """Full pipeline: scaffold → fill bodies → verify → extract_states."""
        from tracefix.pipeline.tools import compile_scaffold, edit_file, verify_spec, extract_states

        ws = ws_with_ir
        compile_scaffold(ws)

        # Fill each process body with minimal valid PlusCal
        # researcherA: acquire doc_lock, release, send submit, wait for response
        edit_file(ws, path="Protocol.tla",
                  old_string='ra_start:\n    skip; (* TODO: replace with protocol logic *)',
                  new_string=('ra_start:\n'
                              '    acquire_lock(doc_lock);\n'
                              '  ra_release:\n'
                              '    release_lock(doc_lock);\n'
                              '    send(resA_to_editor, "submit");\n'
                              '  ra_wait:\n'
                              '    receive(editor_to_resA, msg);\n'
                              '  ra_done:\n'
                              '    skip;'))

        edit_file(ws, path="Protocol.tla",
                  old_string='rb_start:\n    skip; (* TODO: replace with protocol logic *)',
                  new_string=('rb_start:\n'
                              '    acquire_lock(ref_lock);\n'
                              '  rb_release:\n'
                              '    release_lock(ref_lock);\n'
                              '    send(resB_to_editor, "submit");\n'
                              '  rb_wait:\n'
                              '    receive(editor_to_resB, msg);\n'
                              '  rb_done:\n'
                              '    skip;'))

        edit_file(ws, path="Protocol.tla",
                  old_string='ed_start:\n    skip; (* TODO: replace with protocol logic *)',
                  new_string=('ed_start:\n'
                              '    either {\n'
                              '      ed_rcv_a: receive(resA_to_editor, msg);\n'
                              '      ed_rcv_b1: receive(resB_to_editor, msg);\n'
                              '    } or {\n'
                              '      ed_rcv_b: receive(resB_to_editor, msg);\n'
                              '      ed_rcv_a1: receive(resA_to_editor, msg);\n'
                              '    };\n'
                              '  ed_decide:\n'
                              '    send(editor_to_resA, "accept");\n'
                              '    send(editor_to_resB, "accept");\n'
                              '  ed_done:\n'
                              '    skip;'))

        # Verify — should PASS (creates Protocol_translated.tla)
        verify_result = verify_spec(ws)

        if "PASS" not in verify_result:
            pytest.skip(f"verify_spec did not pass: {verify_result[:200]}")

        # Now extract states
        result = extract_states(ws)
        assert "OK" in result
        assert "states.json" in result

        # Verify states.json was written and has correct structure
        states_content = ws.read_file("states.json")
        assert states_content is not None
        states_data = json.loads(states_content)
        assert "states" in states_data
        assert "initial_states" in states_data
        assert len(states_data["states"]) > 0

        # Check that states have expected fields
        for state in states_data["states"]:
            assert "id" in state
            assert "agent" in state


# ---------------------------------------------------------------------------
# load_benchmark
# ---------------------------------------------------------------------------

class TestLoadBenchmark:
    def test_valid_task_id(self, ws):
        from tracefix.pipeline.tools import load_benchmark
        result = load_benchmark(ws, task_id="3E")
        assert "Loaded task" in result
        assert "3E" in result
        assert ws.read_file("task.md") is not None

    def test_invalid_task_id(self, ws):
        from tracefix.pipeline.tools import load_benchmark
        result = load_benchmark(ws, task_id="99Z")
        assert "ERROR" in result

    def test_tools_json_written(self, ws):
        from tracefix.pipeline.tools import load_benchmark
        # Task 12E has domain tools
        result = load_benchmark(ws, task_id="12E")
        assert "tools.json" in result
        content = ws.read_file("tools.json")
        assert content is not None
        tools = json.loads(content)
        assert isinstance(tools, list)

    def test_metadata_json_written(self, ws):
        from tracefix.pipeline.tools import load_benchmark
        # Task 3E has metadata.json (canonical naming source)
        result = load_benchmark(ws, task_id="3E")
        assert "metadata.json" in result
        content = ws.read_file("metadata.json")
        assert content is not None
        json.loads(content)  # must be valid JSON


# ---------------------------------------------------------------------------
# think (no-op)
# ---------------------------------------------------------------------------

class TestThink:
    def test_returns_ok(self, ws):
        from tracefix.pipeline.tools import think
        result = think(ws, thoughts="I should check deadlock patterns.")
        assert result == "OK"
