# TraceFix: Repairing Agent Coordination Protocols with TLA+ Counterexamples

A research platform for verifying LLM-based Multi-Agent Systems (MAS) using TLA+ formal methods. LLMs design coordination protocols as an Intermediate Representation (IR), which compiles to TLA+ specs verified by the TLC model checker. A repair loop fixes violations automatically.

> Reference implementation accompanying the CAIS 2026 paper *"TraceFix: Repairing Agent Coordination Protocols with TLA+ Counterexamples"*.

## Demo

https://github.com/user-attachments/assets/110307e8-9fba-4249-9545-5d577918c6a0

## Quick Start

**1. Install** — the Python package plus the two external tools TraceFix shells out to:
the **TLC** model checker (the *verify* half) and the **opencode** CLI (the *run* half).

> **Platform:** TraceFix runs on **macOS and Linux**. On **Windows, use WSL2** (e.g. Ubuntu)
> and run everything below *inside the WSL shell* — native Windows / Git Bash is not supported.

```bash
git clone https://github.com/Sensing-And-Reasoning/TraceFix.git tracefix
cd tracefix
python -m venv .venv && source .venv/bin/activate
pip install -e ".[agentic,opencode]"            # Python: design/verify + run-harness deps
bash scripts/download_tla2tools.sh              # TLC model checker  (the verify half)
curl -fsSL https://opencode.ai/install | bash   # opencode CLI       (the run half; or: npm i -g opencode-ai)
tla-verify-pluscal doctor                       # check Java 17 + jar + tree-sitter
```

| Prerequisite | Needed for | Notes |
|---|---|---|
| **Python 3.11+** | everything | |
| **Java 17** | `verify` (TLC) | auto-detected on `PATH` / `$JAVA_HOME` / Homebrew `openjdk@17` |
| **`opencode` CLI** | `tracefix run` (default harness) & `tracefix design` | **stock upstream opencode** — TraceFix drives it via injected config, *not* a fork |
| **bun ≥ 1.3.14** | *only* to build the TUI (step 3) | skip it if you design with the skill instead of the TUI |

> Just verifying, no runs? `pip install -e .` + the TLC jar is enough — you can skip the
> opencode CLI, the API key, and the TUI. (`tla-verify-pluscal verify examples/2pc_minimal` → `PASS`.)

**2. Add your API key** — copy the template and fill in one provider key:

```bash
cp .env.example .env
# then edit .env and set ONE of:
#   OPENAI_API_KEY=sk-...
#   ANTHROPIC_API_KEY=sk-ant-...
#   OPENROUTER_API_KEY=...
```

`.env` is gitignored and **auto-loaded from the repo root** — no `source` needed.

**3. Design and run a protocol — with the TUI (recommended)**

The TraceFix TUI is the intended experience: describe what your agents need to coordinate in plain language, and it asks clarifying questions, pauses for your approval, then verifies the protocol and writes each agent's prompts.

```bash
./tui/build-tui.sh        # build the TUI once (needs bun >= 1.3.14)
tracefix-tui              # launch from this repo, then type:
#  /design  Three engineers share one staging server — a builder, a tester, and a
#           deployer that hand off in order. Coordinate them so nothing conflicts.
```

When it finishes, run the whole multi-agent system with the command it prints — this uses
the `opencode` CLI from step 1 (each agent is one opencode process):

```bash
tracefix run --workspace workspace/<name>      # add --live for the browser view
```

> **Prefer not to build the TUI?** The same workflow runs as the `/tla-verify-pluscal`
> skill in Claude Code, or headless via `tracefix design "<requirement>"` — see
> [The full flow](#the-full-flow-requirement--running-mas). Both still use the `opencode`
> CLI for the `run` step.

## Core Idea

LangGraph-style centralized orchestration avoids concurrency — but also limits scalability. This project targets **independent concurrent agents** with shared resources and message channels, where coordination bugs (deadlocks, race conditions, liveness failures) are real risks.

**The pipeline:**
1. LLM generates an Intermediate Representation (IR) describing agents, resources, and channels
2. IR compiles to a TLA+ specification via PlusCal
3. TLC model checker exhaustively explores all interleavings
4. If verification fails, the counterexample trace guides LLM repair
5. Post-verification, state machines are extracted and per-agent runtime prompts are generated

TLC doesn't check business logic — it checks coordination: *"Can two agents hold the same lock? Can the system deadlock? Does every agent eventually terminate?"*

## Project Structure

```
.
├── tracefix/                       # Main package
│   ├── pipeline/                   # Agentic verification pipeline (IR → PlusCal → TLA+)
│   ├── cli/                        # CLI tool: tla-verify-pluscal
│   └── runtime/
│       ├── monitoring/             # Verified coordination core (monitor + corrector)
│       ├── opencode_adapter/       # Harness: each agent as an opencode process (default)
│       └── coordination/           # Distributed: coord core behind a network boundary
├── benchmark/                      # 48 fully-specified tasks + an underspecified narrative tier
├── tui/                            # Recipe to build the TraceFix TUI (a thin opencode fork)
├── .claude/skills/                 # Claude Code interactive skills
├── pyproject.toml
└── LICENSE
```

Run the pipeline to generate verified workspaces (`ir.json`, `Protocol.tla`, `states.json`, per-agent prompts) locally — see Quick Start.

## Verification Pipeline

**`tracefix/pipeline/`** — Agentic pipeline (IR → PlusCal → TLA+)
- `pipeline/pluscal_generator.py` → `pluscal_compiler.py` → `pluscal_parser.py` (tree-sitter)
- TLC state space optimizations: ChannelBound CONSTRAINT, agent-specific Next formula, string messages, multi-core TLC (`-workers auto`), safety-only verification
- One channel per directed (from, to) pair — `labels` field distinguishes message types

**`tracefix/cli/`** — CLI tool (installed via `pip install -e .`)
- Commands: `validate`, `scaffold`, `verify`, `extract-states`

## Benchmarks

**`benchmark/`** — 16 scenarios × 3 difficulties = 48 coordination tasks

| # | Scenario | # | Scenario |
|---|----------|---|----------|
| 1 | Shared Codebase Development | 9 | Dining Philosophers |
| 2 | Smart Building | 10 | Parallel Build |
| 3 | Research Writing | 11 | Flexible Manufacturing |
| 4 | Code Collaboration | 12 | Collaborative Kitchen |
| 5 | Medical Consultation | 13 | Pharmaceutical Lab |
| 6 | Codebase Development | 14 | Drug Discovery Pipeline |
| 7 | Document Co-authoring | 15 | Semiconductor Fabrication |
| 8 | API System Development | 16 | CI/CD Pipeline |

Each task has `description.md`, `tools.json` (per-agent tool schemas), and `metadata.json`. Scenarios 12–16 include simulation environments with failure injection (`--difficulty 0-3`). These 48 are the **fully-specified tier** — descriptions enumerate the agents/resources/communication, so they measure extraction + verification + repair.

**`benchmark/underspecified/`** — a **narrative tier**: 6 scenarios rewritten as plain-prose requirements with no agent/resource enumeration, to measure the *design* capability (deriving the coordination structure from a high-level ask). Scored property-based — TLC pass + parent-checklist coverage + recorded assumptions — by `python -m benchmark.underspec_eval --task <id>`.

## Runtime Architectures

All runtimes consume the same TLC-verified spec and provide fine-grained locking (agents run in parallel, blocking only at contention) — unlike LangGraph's global serialization. Agents autonomously call coordination tools (`acquire_lock`, `send_message`, …); the monitor validates every operation against the verified spec and **blocks + corrects** any out-of-order action before it takes effect.

**`tracefix/runtime/monitoring/`** — the verified coordination **core**: the monitor, per-agent state tracker, and corrector that every harness shares.

**`tracefix/runtime/opencode_adapter/`** — the default harness: each agent runs as its own **opencode** process with real `Read`/`Write`/`Edit`/`Bash`, reaching the coordination core over a per-agent MCP server.

**`tracefix/runtime/coordination/`** — puts the coordination core behind a network boundary (one service + per-agent clients) so agents can run as separate processes/machines.

## Orchestration Workflow

```
Task Description
    ↓
Phase 1: Structured Analysis → ir.json
    ↓
    tla-verify-pluscal scaffold ir.json → Protocol.tla + Protocol.cfg
    ↓
Phase 2: Write PlusCal Process Bodies
    ↓
Phase 2.5: Semantic Fidelity Check
    ↓
Phase 3: tla-verify-pluscal verify . → TLC (repair loop on failure)
    ↓
Phase 4: tla-verify-pluscal extract-states . → states.json
    ↓
Phase 5: Generate per-agent prompts → prompts/runtime_a/ + prompts/runtime_b/
```

For the recommended, interactive way to drive this end to end — the TraceFix TUI
first, the `/tla-verify-pluscal` skill second — see [The full flow](#the-full-flow-requirement--running-mas)
below. The pieces below are the underlying steps those entry points automate.

### Using the skill (in your own harness)

```
> /tla-verify-pluscal
"Design a protocol for task 3E (Two-Author Research Report)"
```

### Using the CLI directly

```bash
pip install -e .
tla-verify-pluscal validate ir.json
tla-verify-pluscal scaffold ir.json -o workspace/my_task/
# (edit Protocol.tla to fill in process bodies)
tla-verify-pluscal verify workspace/my_task/
tla-verify-pluscal extract-states workspace/my_task/
```

### Output Artifacts

```
workspace/my_task/
├── ir.json              # IR specification (agents, resources, channels)
├── Protocol.tla         # PlusCal source + translated TLA+
├── Protocol.cfg         # TLC configuration
├── states.json          # Extracted state machine for runtime
├── summary.json         # Repair tracking
└── prompts/
    └── runtime_b/       # Per-agent runtime prompts (control + business steps)
```

## Development

```bash
pip install -e ".[test]" && pytest tracefix/ benchmark/ -q   # run the test suite
python -m tracefix.pipeline --benchmark 3E --verbose         # the raw agentic pipeline (no TUI)
```

[`.github/workflows/verify.yml`](.github/workflows/verify.yml) gates every push on `tla-verify-pluscal verify` + the test suite (no API keys needed); `verify --json` gives a machine-readable verdict. See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full design → verify → execute flow with diagrams.

## The full flow: requirement → running MAS

Two steps, and you never hand-write a protocol.

**1. Build + verify + generate prompts** — state your requirement. Two ways to use TraceFix:

**→ The TraceFix TUI is the primary experience.** A native terminal app (a thin opencode
fork) whose `designer` agent walks you through the design interactively — it asks clarifying
questions, pauses for your approval of the coordination plan, then derives and TLC-verifies
the protocol. Build it once (see [`tui/`](tui/)) and launch:

```bash
tracefix-tui      # then type:  /design  A 3-agent CI/CD pipeline: a builder, a tester, and a
                  #             deployer that share a staging lock and hand off via review messages.
```

**→ Or use the skill in your own harness.** If you already work inside Claude Code (or another
agent harness), run the same design workflow as a skill — same human-in-the-loop review gates,
no separate binary to build:

```
/tla-verify-pluscal  Design a 3-agent CI/CD pipeline: ...
```

Both run the same workflow — hazard analysis, IR design, PlusCal, TLC verification with an
auto-repair loop, state extraction, and (automatically, as a final step) per-agent prompt
generation — and leave a runnable workspace under `workspace/<name>/` (`spec/` +
`prompts/runtime_b/`). You never write IR or PlusCal by hand.

> For automation (CI, benchmarking, batch design) there is also a non-interactive
> `tracefix design "<requirement>"` that drives the same workflow headlessly with no review
> gate. It is an automation entry point, not the recommended way to design interactively —
> reach for the TUI or the skill for that.

**2. Run the whole system** — one command:

```bash
tracefix run --workspace workspace/<name>
```

This launches every agent on the verified coordination layer using the **opencode**
harness — each agent runs as a stock `opencode` process (the CLI from
[Quick Start](#quick-start); point at another build, e.g. the TUI, with `--opencode-bin`).
The monitor blocks any agent action that would violate the verified protocol. Add `--live`
for the real-time browser view.

Each agent does its **domain work** with the runtime's builtins (read/write/edit/bash) by
default — right for collaborative file/shell tasks. When a step needs a **structured typed
tool** (a real external API, or custom typed logic), the designer tags it in PlusCal
(`[tool: name(args); impl: external|local]`); `extract-states` then generates a per-agent
`tools.json` + impl stub, and the runtime exposes each tool only to its owning agent (over
MCP). So one system can mix builtin collaboration with real typed API calls.

> Want to drive the verify half by hand with no API key? See the [Quick Start](#quick-start)
> CLI path and the bundled, already-verified [`examples/2pc_minimal`](examples/2pc_minimal).

## Verified Properties

TLC exhaustively checks these properties on every generated specification:

| Property | What it verifies |
|----------|-----------------|
| Deadlock freedom | No reachable state where all agents are stuck |
| Mutual exclusion | No lock held by two agents simultaneously |
| Termination | No reachable deadlock before all agents reach their terminal state (deadlock-freedom, a safety property) |
| No orphan locks | All locks freed when protocol completes |
| Channel drainage | All messages consumed when protocol completes |
| Type invariant | All variables maintain valid types throughout execution |

> **Scope:** TraceFix checks **safety only** (the properties above) — not liveness or
> fairness. "Termination" means *no reachable deadlock*, not a proof that every execution
> eventually terminates under all schedulers. TLC also proves the protocol is *coordination*-safe,
> not that the spec faithfully models your intended task (see the semantic-fidelity checklist in the
> `/tla-verify-pluscal` skill).

## IR Schema

The IR has 3 top-level sections: `agents`, `resources`, `channels`.

- **Resources**: `Lock` (mutual exclusion) or `Counter` (non-negative integer). Counter = shared resource pool (API rate limits, GPU slots), NOT loop bounds.
- **Channels**: Unbounded FIFO queues between agents. One channel per directed (from, to) pair; `labels` field distinguishes message types.

Agent behavior is expressed as PlusCal process bodies. State machines are extracted post-verification into `states.json`, which is the ground truth for runtime monitoring and prompt generation.

## Citation

If you use TraceFix in your research, please cite:

```bibtex
@inproceedings{xia2026tracefix,
  title     = {TraceFix: Repairing Agent Coordination Protocols with TLA+ Counterexamples},
  author    = {Xia, Shuren and Li, Qiwei and Ehsan, Taqiya and Ortiz, Jorge},
  booktitle = {ACM Conference on AI and Agentic Systems (CAIS '26)},
  year      = {2026},
  doi       = {10.1145/3786335.3813159}
}
```

## License

MIT — see [LICENSE](LICENSE).
