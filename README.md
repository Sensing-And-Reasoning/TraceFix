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
tracefix/
├── v3_agent_test/          # Agentic verification pipeline (IR → PlusCal → TLA+)
├── tla_verify_pluscal/     # CLI tool: tla-verify-pluscal
├── benchmark/              # 48 coordination tasks (16 scenarios × 3 difficulties)
│
├── runtime_A/              # Architecture A: runtime enforcement engine
├── runtime_B/              # Architecture B: runtime monitoring engine
├── runtime_base_1/         # Baseline: shared-chat (no protocol)
├── runtime_base_2/         # Baseline: null-monitor (no protocol)
│
├── lib/                    # tla2tools.jar (download separately, see Requirements)
└── .claude/skills/         # Claude Code interactive skills
```

Run the pipeline to generate verified workspaces (`ir.json`, `Protocol.tla`, `states.json`, per-agent prompts) locally — see Quick Start.

## Verification Pipeline

**`v3_agent_test/`** — Agentic pipeline (IR → PlusCal → TLA+)
- `pipeline/pluscal_generator.py` → `pluscal_compiler.py` → `pluscal_parser.py` (tree-sitter)
- TLC state space optimizations: ChannelBound CONSTRAINT, agent-specific Next formula, string messages, multi-core TLC (`-workers auto`), safety-only verification
- One channel per directed (from, to) pair — `labels` field distinguishes message types

**`tla_verify_pluscal/`** — CLI tool (installed via `pip install -e .`)
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

**`runtime_A/`** — **Enforcement**: Runtime mediator structurally prevents coordination violations. Agents are unaware of locks/channels.

**`runtime_B/`** — **Monitoring**: Agents autonomously call coordination tools (`acquire_lock`, `send_message`, etc.). Monitor validates every operation against the verified spec.

**`runtime_base_1/`** and **`runtime_base_2/`** — Baselines without protocol monitoring, for comparison experiments.

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
    ├── runtime_a/       # Per-agent prompts for enforcement runtime
    └── runtime_b/       # Per-agent prompts for monitoring runtime
```

## Quick Start

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -e .
pip install openai anthropic pytest

# Run tests
pytest v3_agent_test/tests/ -v             # Pipeline tests
pytest runtime_A/tests/ -v                 # Runtime A tests
pytest runtime_B/tests/ -v                 # Runtime B tests
pytest benchmark/tests/ -v                 # Benchmark tests

# Run the agentic verification pipeline (produces a verified workspace/ )
python -m v3_agent_test --benchmark 3E --verbose

# Runtime B: run agents with monitoring against the generated workspace
python -m runtime_B run --task 3E --workspace workspace/3E --verbose

# Baseline runtimes (no protocol monitoring)
python -m runtime_base_1 run --task 3E --verbose
python -m runtime_base_2 run --task 3E --verbose
```

**Requirements:**
- Python 3.11+ (3.13 tested)
- Java 17 (for TLC): `/opt/homebrew/opt/openjdk@17/bin/java`
- `lib/tla2tools.jar` v1.8.0 (not in git, download from [TLA+ releases](https://github.com/tlaplus/tlaplus/releases))
- API keys in `.env`: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`

## Verified Properties

TLC exhaustively checks these properties on every generated specification:

| Property | What it verifies |
|----------|-----------------|
| Deadlock freedom | No reachable state where all agents are stuck |
| Mutual exclusion | No lock held by two agents simultaneously |
| Termination | All agents eventually reach their terminal state |
| No orphan locks | All locks freed when protocol completes |
| Channel drainage | All messages consumed when protocol completes |
| Type invariant | All variables maintain valid types throughout execution |

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
