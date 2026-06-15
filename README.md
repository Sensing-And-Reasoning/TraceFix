# TraceFix: Repairing Agent Coordination Protocols with TLA+ Counterexamples

A research platform for verifying LLM-based Multi-Agent Systems (MAS) using TLA+ formal methods. LLMs design coordination protocols as an Intermediate Representation (IR), which compiles to TLA+ specs verified by the TLC model checker. A repair loop fixes violations automatically.

> Reference implementation accompanying the CAIS 2026 paper *"TraceFix: Repairing Agent Coordination Protocols with TLA+ Counterexamples"*.

## Demo

https://github.com/user-attachments/assets/110307e8-9fba-4249-9545-5d577918c6a0

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
│       ├── enforcement/            # Architecture A: runtime enforcement engine
│       ├── monitoring/             # Architecture B: runtime monitoring engine
│       └── baselines/
│           ├── shared_chat/        # Baseline: shared-chat (no protocol)
│           └── null_monitor/       # Baseline: null-monitor (no protocol)
├── benchmark/                      # 48 coordination tasks (16 scenarios × 3 difficulties)
├── lib/                            # tla2tools.jar (download separately, see Requirements)
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

Each task has `description.md`, `tools.json` (per-agent tool schemas), and `metadata.json`. Scenarios 12–16 include simulation environments with failure injection (`--difficulty 0-3`).

## Runtime Architectures

Both consume the same TLC-verified spec and provide fine-grained locking (agents run in parallel, blocking only at contention) — unlike LangGraph's global serialization.

**`tracefix/runtime/enforcement/`** — **Enforcement**: Runtime mediator structurally prevents coordination violations. Agents are unaware of locks/channels.

**`tracefix/runtime/monitoring/`** — **Monitoring**: Agents autonomously call coordination tools (`acquire_lock`, `send_message`, etc.). Monitor validates every operation against the verified spec.

**`tracefix/runtime/baselines/shared_chat/`** and **`tracefix/runtime/baselines/null_monitor/`** — Baselines without protocol monitoring, for comparison experiments.

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

### Using Claude Code (Recommended)

```
> /tla-verify-pluscal
"Design a protocol for task 3E (Two-Author Research Report)"
```

### Using CLI Directly

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

## Quick Start

```bash
# Setup (core design+verify — no API key needed)
python -m venv .venv && source .venv/bin/activate
pip install -e .
bash scripts/download_tla2tools.sh    # fetch + checksum tla2tools.jar v1.8.0
tla-verify-pluscal doctor             # confirm Java 17 + jar + tree-sitter

# Verify the bundled example end-to-end — no LLM, no API key
tla-verify-pluscal validate examples/2pc_minimal/ir.json
tla-verify-pluscal verify   examples/2pc_minimal          # → PASS
tla-verify-pluscal extract-states examples/2pc_minimal    # → states.json

# Run the test suite
pip install -e ".[test]"
pytest tracefix/ benchmark/ -q

# Agentic pipeline + runtime (needs an API key: cp .env.example .env)
pip install -e ".[agentic]"
python -m tracefix.pipeline --benchmark 3E --verbose
python -m tracefix.runtime.monitoring run --task 3E --workspace workspace/3E --verbose
```

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full design+verify → execute flow (with diagrams).

**Continuous verification:** [`.github/workflows/verify.yml`](.github/workflows/verify.yml) gates every push on `tla-verify-pluscal verify` + the test suite (no API keys needed). Copy it as a template to gate your own specs — `verify --json` gives a machine-readable verdict and a non-zero exit fails the job.

**Requirements:**
- Python 3.11+ (3.13 tested)
- Java 17 (for TLC) — auto-detected on `PATH` / `$JAVA_HOME` / Homebrew `openjdk@17`; override with `TLA_VERIFY_JAVA` or `--java-path`
- `lib/tla2tools.jar` v1.8.0 — fetched by `scripts/download_tla2tools.sh` (or set `TLA_VERIFY_JAR`)
- API keys (only for the agentic pipeline / runtimes): copy `.env.example` → `.env`

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

This launches every agent on the verified coordination layer (the **opencode** harness by
default; `--harness sdk` for the Claude Agent SDK). The monitor blocks any agent action
that would violate the verified protocol. Add `--live` for the real-time browser view.

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
