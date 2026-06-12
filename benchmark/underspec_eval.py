"""Underspecified (narrative) benchmark tier — scores the DESIGN capability.

The 48 tasks under benchmark/descriptions/ are the fully-specified tier: the
description enumerates agents, shared resources, and communication, so they
measure extraction + compilation + verification + repair against canonical IDs.
This tier measures the other half of "NL requirement -> verified MAS": each task
in benchmark/underspecified/ is the same scenario rewritten as plain narrative
prose (no agent/resource enumeration, no canonical IDs), the way a real user
would describe it. The designer must derive the coordination structure itself.

Because there is no single ground-truth IR, scoring is property-based, not
ID-match-based:
  1. design completes (states.json + one prompt per IR agent)  [mechanical]
  2. TLC PASS as recorded in spec/summary.json                  [mechanical]
  3. plan.md records the structural assumptions (## Assumptions) [mechanical]
  4. every parent-checklist requirement is satisfied by the designed
     protocol (ir.json + plan.md), judged by an LLM               [1 LLM call]

Usage (needs the design model's API key in .env, and the judge's):
    python -m benchmark.underspec_eval --task 12E
    python -m benchmark.underspec_eval --all --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TIER = REPO / "benchmark" / "underspecified"
ENVS = REPO / "benchmark" / "environments"

DEFAULT_TIMEOUT = 1200.0


def tier_tasks() -> list[str]:
    return sorted(p.name for p in TIER.iterdir() if (p / "description.md").exists())


def load_narrative(task_id: str) -> dict:
    """Narrative text + parent checklist for one tier task."""
    d = TIER / task_id
    meta = json.loads((d / "meta.json").read_text())
    checklist = json.loads((ENVS / meta["parent"] / "checklist.json").read_text())
    return {
        "id": task_id,
        "parent": meta["parent"],
        "title": meta.get("title", task_id),
        "narrative": (d / "description.md").read_text().strip(),
        "checklist": checklist,
    }


# ---------------------------------------------------------------------------
# Checklist judge (the only LLM-scored part)
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = """\
You judge whether a designed multi-agent coordination protocol satisfies a set
of benchmark requirements. The design was produced from narrative prose, so the
designer chose its own agent/resource/channel names — judge by STRUCTURE and
SEMANTICS, never by name matching. A requirement is covered only if the design
actually enforces or represents it (an exclusive resource modeled as a Lock, an
ordering dependency carried by a channel the dependent agent receives on, a
revision path modeled as a real branch). Be strict: "probably intended" is not
covered. Return JSON only."""

_JUDGE_USER = """\
## Requirements (parent checklist)
{checklist}

## Designed IR (spec/ir.json)
{ir}

## Designer's plan + assumptions (plan.md)
{plan}

For EACH requirement, decide covered true/false with one line of evidence
naming the IR element (or its absence) that decides it.

Return JSON: {{"items": [{{"id": "<requirement id>", "covered": true/false,
"evidence": "<one line>"}}]}} — one entry per requirement, same ids, no extras."""


def judge_checklist(checklist: list[dict], ir_text: str, plan_text: str,
                    provider: str, model: str) -> list[dict]:
    from tracefix.pipeline.pipeline.llm_client import LLMClient, LLMConfig

    key_env = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
               "openrouter": "OPENROUTER_API_KEY"}[provider]
    api_key = os.environ.get(key_env, "")
    if not api_key:
        raise RuntimeError(f"{key_env} not set — needed for the checklist judge")

    cfg = LLMConfig(provider=provider, model=model, api_key=api_key,
                    base_url="https://openrouter.ai/api/v1" if provider == "openrouter" else "")
    user = _JUDGE_USER.format(
        checklist=json.dumps(checklist, indent=1),
        ir=ir_text or "(missing)",
        plan=plan_text or "(missing)",
    )
    resp = LLMClient(cfg).chat(_JUDGE_SYSTEM, user,
                               response_format={"type": "json_object"} if provider != "anthropic" else None)
    text = resp.content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n|\n```$", "", text)
    items = json.loads(text)["items"]
    by_id = {i["id"]: i for i in items}
    # Missing entries count as not covered — the judge must answer every item.
    return [by_id.get(c["id"], {"id": c["id"], "covered": False,
                                "evidence": "judge returned no entry"}) for c in checklist]


# ---------------------------------------------------------------------------
# Per-task evaluation
# ---------------------------------------------------------------------------

@dataclass
class TierResult:
    task: str
    parent: str
    status: str
    tlc_passed: bool | None
    agents: list[str]
    prompts: int
    assumptions_recorded: bool
    checklist_total: int
    checklist_covered: int | None      # None = judge not run (design incomplete)
    coverage: float | None
    passed: bool
    workspace: str
    duration: float
    items: list[dict] = field(default_factory=list)


def _read(p: Path) -> str:
    return p.read_text() if p.exists() else ""


async def eval_task(task_id: str, *, model: str | None, judge_provider: str,
                    judge_model: str, timeout: float, min_coverage: float,
                    verbose: bool) -> TierResult:
    from tracefix.runtime.opencode_adapter.design import run_design

    t = load_narrative(task_id)
    res = await run_design(t["narrative"], name=f"underspec_{task_id.lower()}",
                           model=model, timeout=timeout, verbose=verbose)
    ws = Path(res.workspace)
    plan = _read(ws / "plan.md")
    assumptions = bool(re.search(r"^#+\s*assumptions", plan, re.I | re.M))

    covered = coverage = None
    items: list[dict] = []
    ir_text = _read(ws / "spec" / "ir.json")
    if res.success and ir_text:
        items = judge_checklist(t["checklist"], ir_text, plan, judge_provider, judge_model)
        covered = sum(1 for i in items if i.get("covered"))
        coverage = covered / len(t["checklist"]) if t["checklist"] else 1.0

    passed = bool(res.success and res.tlc_passed and assumptions
                  and coverage is not None and coverage >= min_coverage)
    return TierResult(
        task=task_id, parent=t["parent"], status=res.status,
        tlc_passed=res.tlc_passed, agents=res.agents, prompts=len(res.prompts),
        assumptions_recorded=assumptions, checklist_total=len(t["checklist"]),
        checklist_covered=covered, coverage=coverage, passed=passed,
        workspace=res.workspace, duration=round(res.duration, 1), items=items,
    )


def main(argv: list[str] | None = None) -> int:
    try:  # provider keys live in .env at the repo root
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env")
    except ImportError:
        pass

    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--task", help="tier task id (see benchmark/underspecified/)")
    g.add_argument("--all", action="store_true", help="run every tier task sequentially")
    ap.add_argument("--model", help="design model as provider/id (tracefix design --model)")
    ap.add_argument("--judge-provider", default="openai",
                    choices=["openai", "anthropic", "openrouter"])
    ap.add_argument("--judge-model", default="gpt-5-mini")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    ap.add_argument("--min-coverage", type=float, default=1.0,
                    help="checklist coverage required to pass (default: all items)")
    ap.add_argument("--json", action="store_true", help="machine-readable verdicts")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    tasks = tier_tasks() if args.all else [args.task]
    missing = [t for t in tasks if not (TIER / t / "description.md").exists()]
    if missing:
        print(f"unknown tier task(s): {missing} — available: {tier_tasks()}", file=sys.stderr)
        return 2

    results = []
    for t in tasks:
        r = asyncio.run(eval_task(
            t, model=args.model, judge_provider=args.judge_provider,
            judge_model=args.judge_model, timeout=args.timeout,
            min_coverage=args.min_coverage, verbose=args.verbose))
        results.append(r)
        if args.json:
            print(json.dumps(asdict(r)))
        else:
            cov = "-" if r.coverage is None else f"{r.checklist_covered}/{r.checklist_total}"
            print(f"[{'PASS' if r.passed else 'FAIL'}] {r.task}  status={r.status} "
                  f"tlc={r.tlc_passed} coverage={cov} assumptions={r.assumptions_recorded} "
                  f"({r.duration}s)  {r.workspace}")
            for i in r.items:
                if not i.get("covered"):
                    print(f"         MISSING {i['id']}: {i.get('evidence', '')}")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
