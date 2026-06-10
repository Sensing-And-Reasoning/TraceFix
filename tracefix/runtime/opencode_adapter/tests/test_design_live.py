"""Design-phase live view: artifact watcher narration + page rendering."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from tracefix.runtime.opencode_adapter.design import DesignWatcher
from tracefix.runtime.opencode_adapter.design_view import render_design_html


class FakeBus:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    async def emit(self, event: str, data: dict):
        self.events.append((event, data))

    def types(self):
        return [e for e, _ in self.events]


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "spec").mkdir(parents=True)
    return ws


def test_watcher_ignores_the_init_stub_ir(tmp_path):
    ws = _ws(tmp_path)
    # the init stub: agents only, no channels/resources — not a designed IR yet
    (ws / "spec" / "ir.json").write_text(json.dumps(
        {"agents": [{"id": "AGENT_A"}], "resources": [], "channels": []}))
    bus = FakeBus()
    asyncio.run(DesignWatcher(ws, bus)._tick())
    assert "design.ir" not in bus.types()


def test_watcher_narrates_the_full_artifact_sequence(tmp_path):
    ws = _ws(tmp_path)
    bus = FakeBus()
    w = DesignWatcher(ws, bus)

    async def scenario():
        # 1) a real IR appears
        (ws / "spec" / "ir.json").write_text(json.dumps({
            "agents": [{"id": "A"}, {"id": "B"}], "resources": [],
            "channels": [{"id": "ab", "from": "A", "to": "B", "labels": ["go"]}]}))
        await w._tick()
        # 2) verify fails once, then passes
        (ws / "spec" / "summary.json").write_text(json.dumps(
            {"tlc_passed": False, "total_repairs": 1}))
        await w._tick()
        (ws / "spec" / "summary.json").write_text(json.dumps(
            {"tlc_passed": True, "total_repairs": 1}))
        await w._tick()
        # 3) states + prompts
        (ws / "spec" / "states.json").write_text("{}")
        pdir = ws / "prompts" / "runtime_b"
        pdir.mkdir(parents=True)
        (pdir / "A.md").write_text("# A")
        (pdir / "B.md").write_text("# B")
        await w._tick()

    asyncio.run(scenario())
    types = bus.types()
    assert types.count("design.ir") == 1
    verdicts = [d for e, d in bus.events if e == "design.verdict"]
    assert [v["tlc_passed"] for v in verdicts] == [False, True]
    assert "design.phase" in types
    prompts = [d["agent"] for e, d in bus.events if e == "design.prompt"]
    assert prompts == ["A", "B"]


def test_watcher_emits_each_artifact_once(tmp_path):
    ws = _ws(tmp_path)
    (ws / "spec" / "ir.json").write_text(json.dumps({
        "agents": [{"id": "A"}], "resources": [{"id": "l", "type": "Lock"}],
        "channels": []}))
    bus = FakeBus()
    w = DesignWatcher(ws, bus)

    async def scenario():
        await w._tick()
        await w._tick()   # unchanged artifacts → no re-emission

    asyncio.run(scenario())
    assert bus.types().count("design.ir") == 1


def test_design_html_renders_phases_and_sse_client():
    html = render_design_html(title="design: demo <x>", model="openai/gpt-5.4")
    assert "design: demo &lt;x&gt;" in html          # title is escaped
    assert "Phase 3 · TLC verify + repair" in html   # phase rail present
    assert 'new EventSource("/api/events")' in html  # SSE client
    assert "design.verdict" in html and "design.ir" in html
