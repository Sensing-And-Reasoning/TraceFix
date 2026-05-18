"""Tests for prompt_gen: PlusCal extraction and prompt generation."""

import json
from pathlib import Path

import pytest

from tracefix.runtime.monitoring.prompt_gen import extract_pluscal_process, generate_agent_prompt

_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
_FIXTURES = Path(__file__).parent / "fixtures"
_3M_IR = _FIXTURES / "3M" / "ir.json"
_3M_TLA = _FIXTURES / "3M" / "Protocol.tla"
_3M_TASK = _ROOT / "benchmark" / "descriptions" / "3M" / "description.md"


@pytest.fixture
def ir_3m():
    with open(_3M_IR) as f:
        return json.load(f)


@pytest.fixture
def tla_source():
    return _3M_TLA.read_text()


@pytest.fixture
def task_desc():
    return _3M_TASK.read_text()


# ---------------------------------------------------------------------------
# PlusCal extraction
# ---------------------------------------------------------------------------

class TestExtractProcess:
    def test_extract_researcherA(self, tla_source):
        body = extract_pluscal_process(tla_source, "researcherA")
        assert "fair process (researcherA_proc" in body
        assert "ra_write:" in body
        assert "ra_done:" in body
        assert "acquire_lock(doc_lock)" in body

    def test_extract_factchecker(self, tla_source):
        body = extract_pluscal_process(tla_source, "factchecker")
        assert "fair process (factchecker_proc" in body
        assert "fc_loop:" in body
        assert "fc_done:" in body
        assert "receive(resA_to_fc, msg)" in body

    def test_extract_editor(self, tla_source):
        body = extract_pluscal_process(tla_source, "editor")
        assert "fair process (editor_proc" in body
        assert "ed_collect:" in body
        assert "ed_done:" in body

    def test_extract_all_five_agents(self, tla_source, ir_3m):
        """All 5 agents in 3M should be extractable."""
        for agent in ir_3m["agents"]:
            body = extract_pluscal_process(tla_source, agent["id"])
            assert f"fair process ({agent['id']}_proc" in body

    def test_extract_nonexistent_raises(self, tla_source):
        with pytest.raises(ValueError, match="not found"):
            extract_pluscal_process(tla_source, "nonexistent_agent")

    def test_process_is_complete(self, tla_source):
        """Extracted process should have balanced braces."""
        body = extract_pluscal_process(tla_source, "researcherA")
        assert body.count("{") == body.count("}")


# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------

class TestGeneratePrompt:
    def test_prompt_contains_agent_id(self, ir_3m, tla_source, task_desc):
        prompt = generate_agent_prompt("researcherA", task_desc, ir_3m, tla_source)
        assert 'You are agent "researcherA"' in prompt

    def test_prompt_contains_task(self, ir_3m, tla_source, task_desc):
        prompt = generate_agent_prompt("researcherA", task_desc, ir_3m, tla_source)
        assert "Multi-Author Paper" in prompt

    def test_prompt_contains_protocol(self, ir_3m, tla_source, task_desc):
        prompt = generate_agent_prompt("researcherA", task_desc, ir_3m, tla_source)
        assert "ra_write:" in prompt
        assert "acquire_lock(doc_lock)" in prompt

    def test_prompt_contains_send_channels(self, ir_3m, tla_source, task_desc):
        prompt = generate_agent_prompt("researcherA", task_desc, ir_3m, tla_source)
        assert "resA_to_fc" in prompt
        assert "resA_to_editor" in prompt

    def test_prompt_contains_receive_channels(self, ir_3m, tla_source, task_desc):
        prompt = generate_agent_prompt("researcherA", task_desc, ir_3m, tla_source)
        assert "fc_to_resA" in prompt
        assert "editor_to_resA" in prompt

    def test_prompt_contains_locks(self, ir_3m, tla_source, task_desc):
        prompt = generate_agent_prompt("researcherA", task_desc, ir_3m, tla_source)
        assert "doc_lock" in prompt
        assert "ref_lock" in prompt

    def test_prompt_contains_rules(self, ir_3m, tla_source, task_desc):
        prompt = generate_agent_prompt("researcherA", task_desc, ir_3m, tla_source)
        assert "Follow your protocol steps in order" in prompt

    def test_factchecker_prompt(self, ir_3m, tla_source, task_desc):
        prompt = generate_agent_prompt("factchecker", task_desc, ir_3m, tla_source)
        assert 'You are agent "factchecker"' in prompt
        assert "fc_loop:" in prompt
        # Factchecker receives from 3 researchers
        assert "resA_to_fc" in prompt
        assert "resB_to_fc" in prompt
        assert "resC_to_fc" in prompt
