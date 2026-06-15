"""``tracefix design`` — drive an UNMODIFIED headless opencode through the
/tla-verify-pluscal skill to turn a natural-language requirement into a
verified, runnable workspace (spec/ + prompts/runtime_b/).

Architecture: the design *knowledge* lives in the skill (SKILL.md + references)
and the *checks* live in the ``tla-verify-pluscal`` CLI — both harness-portable.
opencode is just the engine: this orchestrator injects the skill as the agent's
system prompt (plus a headless preamble), points ``--dir`` at the repo root (so
``.claude/skills/`` references and ``workspace/`` resolve), and judges the
outcome from the ARTIFACTS the run leaves behind, never from the transcript.

No opencode source modification — same principle as the runtime adapter.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from tracefix.runtime.opencode_adapter.config_gen import build_design_config
from tracefix.runtime.opencode_adapter.driver import run_opencode_agent

#: Where the design-workflow skills live, relative to the repo root.
_SKILL = ".claude/skills/tla-verify-pluscal/SKILL.md"
_PROMPT_GEN_SKILL = ".claude/skills/tla-prompt-gen/SKILL.md"

#: A full design+verify+prompts run includes several TLC invocations and up to
#: 5 repair attempts — give it real time by default.
DEFAULT_TIMEOUT = 1800.0


def repo_root() -> Path:
    return next(p for p in Path(__file__).resolve().parents
                if (p / "pyproject.toml").exists())


def slugify(task: str) -> str:
    """A short filesystem-safe workspace name derived from the task text."""
    words = re.findall(r"[a-z0-9]+", task.lower())[:5]
    return "_".join(words) or "design"


_HEADLESS_PREAMBLE = """\
# Headless mode (no interactive user)

You are running non-interactively inside `tracefix design`. Follow the workflow
below with these adjustments:
- NEVER pause to ask the user anything. At the Phase 1.5 review gate, write
  `plan.md` into the workspace and proceed immediately (it is kept for
  after-the-fact review).
- The requirement may be plain prose with no explicit agent/resource lists.
  Derive the coordination structure yourself, and record EVERY structural
  choice the prose does not state outright — how many agents and why, what
  each shared resource is and why it is exclusive (Lock) vs a capacity pool
  (Counter), and the channel topology — in `plan.md` under an
  `## Assumptions` heading. Unrecorded assumptions count as silent guessing.
- Typed tools: most domain work runs on builtins (read/write/edit/bash). If a
  step needs a structured typed tool (a real external API, or custom typed
  logic), tag it in PlusCal `[tool: ...; impl: external|local]` and list it
  (name, owning agent, impl kind) under `## Assumptions` — extract-states turns
  the tags into a generated `tools.json` + impl stub the user binds later.
- "Never pause" means do NOT ask the user — it does NOT mean skip the checks.
  Still do the SKILL.md Phase 1.5 self-critique (verify every hazard, channel,
  ordering constraint, and failure path is represented against the requirement)
  and the MANDATORY Phase 2.5 fidelity check before verifying.
- Where the workflow says to invoke the `/tla-prompt-gen` skill (Phase 5), read
  `{prompt_gen_skill}` and follow it directly on this same workspace instead.
- The skill's reference files live under `.claude/skills/tla-verify-pluscal/references/`
  — read them when the workflow points to them.
- Work ONLY inside the workspace directory given in the task message; run the
  `tla-verify-pluscal` CLI via bash (it is on PATH).
- If verification still fails after 5 attempts, record `"tlc_passed": false` in
  `summary.json`, write an honest failure report, and stop — never fake a pass.

---

"""


def build_designer_prompt(root: Path) -> str:
    """The designer agent's system prompt: headless preamble + the skill itself."""
    skill_text = (root / _SKILL).read_text()
    # Strip the YAML frontmatter (invocation metadata, meaningless to opencode).
    if skill_text.startswith("---"):
        end = skill_text.find("\n---", 3)
        if end != -1:
            skill_text = skill_text[end + 4:]
    preamble = _HEADLESS_PREAMBLE.format(prompt_gen_skill=_PROMPT_GEN_SKILL)
    return preamble + skill_text.lstrip("\n")


def design_kickoff(workspace_rel: str) -> str:
    return (
        f"Design, verify, and generate prompts for the coordination protocol of the "
        f"task described in `{workspace_rel}/description.md`. The workspace is "
        f"`{workspace_rel}/` (already initialized: spec/ir.json is a stub to replace). "
        f"Follow your instructions end to end — finish only when "
        f"`{workspace_rel}/prompts/runtime_b/` holds one prompt per agent."
    )


@dataclass
class DesignResult:
    """Artifact-judged outcome of one design run."""
    success: bool
    workspace: str
    status: str                       # ready | verify_failed | incomplete | timeout | error
    tlc_passed: bool | None = None
    agents: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    repairs: int | None = None
    duration: float = 0.0
    events: int = 0
    stderr_tail: list[str] = field(default_factory=list)


def inspect_workspace(ws: Path) -> dict:
    """Judge a design run purely from its artifacts (transcript-independent)."""
    spec = ws / "spec" if (ws / "spec").is_dir() else ws
    out: dict = {"ir": None, "states": (spec / "states.json").exists(),
                 "tlc_passed": None, "repairs": None, "prompts": []}
    ir_path = spec / "ir.json"
    if ir_path.exists():
        try:
            out["ir"] = json.loads(ir_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    summary = spec / "summary.json"
    if summary.exists():
        try:
            s = json.loads(summary.read_text())
            out["tlc_passed"] = s.get("tlc_passed")
            out["repairs"] = s.get("total_repairs")
        except (json.JSONDecodeError, OSError):
            pass
    pdir = ws / "prompts" / "runtime_b"
    if pdir.is_dir():
        out["prompts"] = sorted(p.stem for p in pdir.glob("*.md"))
    return out


def judge(ws: Path, *, timed_out: bool = False) -> DesignResult:
    info = inspect_workspace(ws)
    agents = [a["id"] for a in (info["ir"] or {}).get("agents", [])
              if isinstance(a, dict) and "id" in a]
    have_all_prompts = bool(agents) and set(agents) <= set(info["prompts"])
    ready = bool(info["tlc_passed"]) and info["states"] and have_all_prompts
    if ready:
        status = "ready"
    elif timed_out:
        status = "timeout"
    elif info["tlc_passed"] is False:
        status = "verify_failed"   # honest failure — capped repair attempts exhausted
    else:
        status = "incomplete"
    return DesignResult(
        success=ready, workspace=str(ws), status=status,
        tlc_passed=info["tlc_passed"], agents=agents,
        prompts=info["prompts"], repairs=info["repairs"],
    )


def _init_workspace(name: str, task: str) -> Path:
    """Create a fresh workspace/<name>_<timestamp>/ via the CLI's init.

    resolve_init_dir does the timestamping (every design run gets a new
    directory, never iterating on an older same-named workspace); passing the
    resolved path to cmd_init keeps the two in agreement on where files land."""
    from tracefix.cli.cli import cmd_init, resolve_init_dir
    out = resolve_init_dir(name)
    cmd_init(argparse.Namespace(dir=str(out), task=task, agents=None, with_tools=False))
    return out.resolve()


class DesignWatcher:
    """Polls the workspace's ARTIFACTS and narrates design progress to the event bus.

    Observability only (the runtime three-plane rule applies here too): the watcher
    renders what the artifacts prove — ir.json written, TLC verdict, states.json,
    prompts appearing — and never influences the design run.
    """

    def __init__(self, ws: Path, bus, poll: float = 1.0):
        self.ws = ws
        self.bus = bus
        self.poll = poll
        self._ir_snapshot: str | None = None
        self._summary_snapshot: str | None = None
        self._prompts_seen: set[str] = set()
        self._states_done = False

    async def _emit(self, event: str, data: dict) -> None:
        await self.bus.emit(event, data)

    async def _tick(self) -> None:
        spec = self.ws / "spec" if (self.ws / "spec").is_dir() else self.ws

        ir_path = spec / "ir.json"
        if ir_path.exists():
            try:
                raw = ir_path.read_text()
            except OSError:
                raw = None
            if raw and raw != self._ir_snapshot:
                try:
                    ir = json.loads(raw)
                except json.JSONDecodeError:
                    ir = None
                # the init stub has no resources/channels — only narrate a real IR
                if ir and ir.get("agents") and (ir.get("channels") or ir.get("resources")):
                    self._ir_snapshot = raw
                    await self._emit("design.phase",
                                     {"key": "ir", "state": "done", "label": "IR designed"})
                    await self._emit("design.ir", {"ir": ir})
                    await self._emit("design.phase",
                                     {"key": "pluscal", "state": "active",
                                      "label": "writing PlusCal bodies"})

        summary = spec / "summary.json"
        if summary.exists():
            try:
                raw = summary.read_text()
            except OSError:
                raw = None
            if raw and raw != self._summary_snapshot:
                self._summary_snapshot = raw
                try:
                    s = json.loads(raw)
                except json.JSONDecodeError:
                    s = {}
                await self._emit("design.phase",
                                 {"key": "verify", "state": "active", "label": "TLC verify"})
                if "tlc_passed" in s and (s["tlc_passed"] or s.get("total_repairs")):
                    await self._emit("design.verdict",
                                     {"tlc_passed": s.get("tlc_passed"),
                                      "repairs": s.get("total_repairs")})

        if not self._states_done and (spec / "states.json").exists():
            self._states_done = True
            await self._emit("design.phase",
                             {"key": "states", "state": "done", "label": "states extracted"})

        pdir = self.ws / "prompts" / "runtime_b"
        if pdir.is_dir():
            total = len((json.loads(self._ir_snapshot) or {}).get("agents", [])) \
                if self._ir_snapshot else 0
            for p in sorted(pdir.glob("*.md")):
                if p.stem not in self._prompts_seen:
                    self._prompts_seen.add(p.stem)
                    await self._emit("design.prompt",
                                     {"agent": p.stem, "count": len(self._prompts_seen),
                                      "total": total or "?"})

    async def run(self) -> None:
        await self._emit("design.phase",
                         {"key": "toolchain", "state": "active", "label": "starting designer"})
        try:
            while True:
                await self._tick()
                await asyncio.sleep(self.poll)
        except asyncio.CancelledError:
            await self._tick()   # final sweep so late artifacts still render
            raise


async def run_design(
    task: str,
    *,
    name: str | None = None,
    model: str | None = None,
    opencode_cmd: list[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    on_event: Callable[[str, dict], None] | None = None,
    verbose: bool = False,
    live: bool = False,
    live_port: int = 8765,
    live_warmup: float = 3.0,
    live_hold: float = 0.0,
) -> DesignResult:
    """One full design run: requirement in, verified workspace out."""
    root = repo_root()
    name = name or slugify(task)
    ws = _init_workspace(name, task)
    ws_rel = str(ws.relative_to(root))

    prompt = build_designer_prompt(root)
    cfg = build_design_config(prompt, model=model)

    # Optional live view: same SSE stack as the runtime, design-phase page.
    bus = server = watcher_task = None
    if live:
        from tracefix.runtime.monitoring.event_bus import EventBus
        from tracefix.runtime.monitoring.live_server import start_live_server
        from tracefix.runtime.opencode_adapter.design_view import render_design_html

        bus = EventBus()
        server = await start_live_server(
            {}, bus, port=live_port,
            html=render_design_html(title=f"design: {name}", model=model or ""))
        url = f"http://127.0.0.1:{live_port}"
        print(f"[design] live view: {url}", file=sys.stderr)
        import webbrowser
        webbrowser.open(url)
        if live_warmup > 0:
            await asyncio.sleep(live_warmup)
        watcher_task = asyncio.create_task(DesignWatcher(ws, bus).run())

        user_on_event = on_event

        def _tap(agent_id: str, ev: dict) -> None:
            if user_on_event is not None:
                user_on_event(agent_id, ev)
            if ev.get("type") == "tool_use":
                part = ev.get("part") or {}
                asyncio.get_running_loop().create_task(bus.emit("design.tool", {
                    "tool": part.get("tool"),
                    "status": (part.get("state") or {}).get("status"),
                }))
        on_event = _tap

    # Same process hygiene as the runtime adapter: per-run XDG data/state (keep the
    # user's opencode state clean; cache stays shared for the warm ripgrep), and the
    # venv's bin on PATH so `tla-verify-pluscal` resolves inside opencode's bash.
    inst = ws / ".design"
    for sub in ("data", "state"):
        (inst / sub).mkdir(parents=True, exist_ok=True)
    venv_bin = str(Path(sys.executable).resolve().parent)
    env = {
        "XDG_DATA_HOME": str(inst / "data"),
        "XDG_STATE_HOME": str(inst / "state"),
        "PATH": venv_bin + os.pathsep + os.environ.get("PATH", ""),
    }

    if verbose:
        print(f"[design] workspace={ws_rel} model={model or '(opencode default)'} "
              f"timeout={timeout:.0f}s", file=sys.stderr)

    start = time.time()
    disposition = await run_opencode_agent(
        "designer", cfg,
        opencode_cmd=opencode_cmd or ["opencode"],
        output_dir=root,                      # --dir = repo root: skills + workspace/ resolve
        kickoff=design_kickoff(ws_rel),
        timeout=timeout,
        on_event=on_event,
        env_overrides=env,
    )

    result = judge(ws, timed_out=disposition["status"] == "timeout")
    result.duration = time.time() - start
    result.events = disposition.get("events", 0)
    result.stderr_tail = disposition.get("stderr_tail", [])
    if result.status == "incomplete" and disposition.get("returncode") not in (0, None):
        result.status = "error"

    if live and bus is not None:
        if watcher_task is not None:
            watcher_task.cancel()
            try:
                await watcher_task
            except asyncio.CancelledError:
                pass
        await bus.emit("design.done", {"status": result.status, "workspace": ws_rel})
        if live_hold > 0:
            await asyncio.sleep(live_hold)
        else:
            await asyncio.sleep(1.0)  # let the browser drain the final events
        if server is not None:
            from tracefix.runtime.monitoring.live_server import stop_live_server
            await stop_live_server(server)

    return result
