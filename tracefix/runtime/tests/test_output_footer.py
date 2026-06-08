"""The runtime output-footer tells each agent its shared area + private dir."""

from __future__ import annotations

from pathlib import Path

from tracefix.runtime.sdk_adapter.orchestrator import SdkOrchestrator
from tracefix.runtime.opencode_adapter.orchestrator import OpencodeOrchestrator


def _check_footer(footer: str, out: Path, agent_id: str):
    assert str((out / "shared").resolve()) in footer        # shared area
    assert str((out / agent_id).resolve()) in footer         # this agent's private dir
    assert (out / "shared").is_dir() and (out / agent_id).is_dir()  # created
    lo = footer.lower()
    assert "shared" in lo and "private" in lo


def test_sdk_footer_names_shared_and_private(tmp_path):
    orch = SdkOrchestrator("t", tmp_path)
    orch.run_dir = tmp_path / "output"
    orch.run_dir.mkdir()
    _check_footer(orch._output_footer("AGENT_A"), orch.run_dir, "AGENT_A")


def test_opencode_footer_names_shared_and_private(tmp_path):
    orch = OpencodeOrchestrator("t", tmp_path)
    orch.run_dir = tmp_path / "output"
    orch.run_dir.mkdir()
    _check_footer(orch._output_footer("AGENT_B"), orch.run_dir, "AGENT_B")
