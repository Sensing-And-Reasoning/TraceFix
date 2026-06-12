# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TraceFix verifies LLM multi-agent coordination protocols using TLA+ formal methods. The pipeline turns natural-language task descriptions into a verified Intermediate Representation (IR), compiles it through PlusCal to TLA+, model-checks it with TLC, and emits per-agent runtime prompts. Two runtimes — `monitoring` (built-in OpenAI loop) and `sdk_adapter` (Claude Agent SDK harness, real Read/Write/Edit/Bash) — consume the verified artifacts; an opt-in `coordination` service distributes them across processes/machines.

## Common Commands

### Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .                 # core: design+verify works offline (no API key)
pip install -e ".[agentic]"      # + openai/anthropic, only for the LLM pipeline/runtimes
pip install -e ".[test]"         # + pytest/pytest-asyncio, to run the test suite
bash scripts/download_tla2tools.sh   # fetch + checksum the pinned tla2tools.jar v1.8.0
tla-verify-pluscal doctor        # confirm Java 17 + jar + tree-sitter (runs a smoke test)
```

`pip install -e .` now installs everything the no-LLM verify path needs (jsonschema,
tree-sitter, tree-sitter-tlaplus, python-dotenv). External requirements not handled by pip:
- **Java 17** — auto-detected via `TLA_VERIFY_JAVA` → Homebrew `openjdk@17` → `$JAVA_HOME` → `java` on `PATH`; override with `--java-path`. `doctor` reports the resolved path.
- **`lib/tla2tools.jar`** v1.8.0 — fetched by `scripts/download_tla2tools.sh` (override with `TLA_VERIFY_JAR` env var or `--jar-path`).
- **API keys** in `.env` at repo root (copy `.env.example`): only the agentic pipeline/runtimes need them — `validate`/`scaffold`/`verify`/`extract-states` do not. Keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` (also `OPENROUTER_API_KEY` for OpenRouter).

### Verification CLI
After `pip install -e .`, the `tla-verify-pluscal` entry point is on PATH (`tracefix.cli.cli:main`):
```bash
tla-verify-pluscal doctor                            # check Java 17 + jar + tree-sitter (+ smoke-test examples/2pc_minimal)
tla-verify-pluscal validate ir.json                  # IR schema + semantic checks
tla-verify-pluscal scaffold ir.json -o workspace/    # → Protocol.tla + Protocol.cfg
tla-verify-pluscal verify workspace/                 # PlusCal translate + TLC (--json for a machine-readable verdict; failed attempts archived to workspace/history/attempt_N/)
tla-verify-pluscal extract-states workspace/         # Translated TLA+ → states.json (--strict to fail on warnings, not just parse errors)
```

### Agentic Pipeline (end-to-end)
```bash
python -m tracefix.pipeline --benchmark 3E --verbose
python -m tracefix.pipeline --benchmark-all --difficulty E --parallel 3
python -m tracefix.pipeline --prompt-gen-only path/to/workspace  # Phase 5 only
python -m tracefix.pipeline --task "Design a 2PC protocol with coordinator and 2 banks"
```
Provider/model: `--provider openai|anthropic|openrouter` `--model gpt-5` `--reasoning-effort high` `--thinking-budget N` `--max-turns 40`.

### Design (headless, no Claude Code needed)
`tracefix design "<requirement>"` drives an **unmodified** headless opencode through the
`/tla-verify-pluscal` skill (injected as the agent prompt + a non-interactive preamble;
Phase 5 reads the prompt-gen skill directly) and judges the outcome from artifacts
(`spec/states.json` + `summary.json.tlc_passed` + one prompt per IR agent). Flags:
`--name`, `--model provider/id`, `--timeout`, `--live` (design-phase browser view:
phase rail, IR topology, TLC verdict, activity feed — same SSE stack as the runtime).
See `tracefix/runtime/opencode_adapter/design.py` (+ `design_view.py`).

### Runtimes
The unified front door is `tracefix run` (console script). It runs a verified workspace
through a harness — default **opencode** — with a friendly preflight; `--task` is derived
from the workspace folder name, and unknown flags pass through to the chosen harness:
```bash
tracefix run --workspace workspace/3E                      # opencode (default)
tracefix run --workspace workspace/3E --harness sdk --model gpt-5-mini
tracefix run --workspace workspace/3E --harness monitoring --verbose   # benchmark sim
```
The per-harness module CLIs remain available for full control:
```bash
# Monitoring (Architecture B, OpenAI loop) — agents call coordination tools, Monitor validates
python -m tracefix.runtime.monitoring run --task 3E --workspace workspace/3E --verbose

# SDK adapter (Architecture B, Claude Agent SDK harness) — real Read/Write/Edit/Bash;
# run sub-agents on OpenAI via a LiteLLM proxy (ANTHROPIC_BASE_URL → proxy)
python -m tracefix.runtime.sdk_adapter run --task 3E --workspace workspace/3E \
    --model gpt-5-mini --builtins Read,Write,Edit
```
The `coordination/` service (CoordClient/CoordinationService/CoordBackend) is the
inter-process backbone the opencode runtime starts in-process every run; agents reach it
over loopback. A standalone multi-machine launcher is not shipped (restore one from git
history if real distributed deployment is needed).
Add `--live` (sdk_adapter: `--live-port`/`--live-warmup`/`--live-hold`) for real-time D3 + SSE visualization in the browser. Sim-enabled scenarios (12–16) accept `--difficulty 0-3`, `--scenario N`, `--tool-time FLOAT`, `--seed INT`.

**Workspaces (repo cleanliness):** `tla-verify-pluscal init <name>` creates `workspace/<name>_<timestamp>/` (**gitignored**; the timestamp suffix makes every init a fresh workspace — designs never iterate on an older same-named dir; an explicit path skips the suffix), organized into subfolders: **`spec/`** (verification artifacts — `ir.json`, `Protocol*.tla`, `Protocol.cfg`, `states.json`, `summary.json`, tlc logs, `history/`), **`prompts/`** (per-agent prompts), **`output/`** (runtime artifacts the agents produce). Inputs `description.md` / `tools.json` sit at the workspace root. The runtimes resolve spec files via `tracefix/runtime/workspace_layout.py` (backward-compatible: a flat workspace with everything at the root still works). Within a run's `output/`, agents share **`output/shared/`** (their cwd — handoff/coordinated files; the protocol's locks protect these) and each gets a private **`output/<agent>/`** for files only it uses (its own tests, scratch, intermediate work). The sdk_adapter pins agents' file writes to these absolute dirs in the prompt footer (the claude CLI resolves relative writes against the git root, not cwd); opencode sets `--dir` to the shared area. Curated, committed examples live separately under `tracefix/runtime/sdk_adapter/examples/`.

### Tests
```bash
pytest tracefix/pipeline/tests/ -v
pytest tracefix/runtime/monitoring/tests/ -v
pytest tracefix/runtime/sdk_adapter/tests/ -v
pytest tracefix/runtime/coordination/tests/ -v
pytest benchmark/tests/ -v
pytest tracefix/runtime/monitoring/tests/test_coord.py -v   # needs pytest-asyncio (pip install -e ".[test]")
```

## High-Level Architecture

### 1. Verification Pipeline (`tracefix/pipeline/`)
Two layers stacked together:

**Outer layer (`tracefix/pipeline/`)** — agentic loop that drives the inner pipeline via LLM tool calls.
- `cli.py` — entry point, benchmark runner, parallel executor
- `loop.py` — think-act-observe loop with context compression and doom-loop detection
- `tool_client.py` — provider-agnostic LLM client (OpenAI / Anthropic / OpenRouter)
- `tools.py` — 10 tool schemas + implementations wrapping the inner pipeline
- `prompts.py` — system prompt embedding IR schema, anti-patterns, 2PC example
- `workspace.py` — file-based session directory (`ir.json`, `Protocol.tla`, logs)
- `session.py` — session recording

**Inner layer (`tracefix/pipeline/pipeline/`)** — pure deterministic compilation pipeline.
- `validator.py` (`schema.json`) — IR schema + semantic validation (channel labels)
- `pluscal_generator.py` — IR → PlusCal scaffold (`Protocol.tla`) + TLC config
- `pluscal_compiler.py` — PlusCal → translated TLA+ (calls `pcal.trans` from `tla2tools.jar`)
- `tlc_runner.py` — TLC subprocess (`-workers auto`, `-Xmx4g`, safety-only)
- `trace_parser.py` + `error_formatter.py` — TLC counterexample → human-readable repair prompt
- `pluscal_parser.py` (tree-sitter) — extract per-agent state machine into `states.json`
- `tla_parser.py` — legacy regex parser (kept behind `--legacy` flag)

State-space optimizations baked into the generators: `ChannelBound` CONSTRAINT, per-agent `Next` disjunction, string messages (not records), one channel per directed (from, to) pair (`labels` discriminates message types), safety-only verification.

### 2. CLI (`tracefix/cli/`)
Thin argparse wrapper around the inner pipeline. `cli.py:_resolve_java` / `_resolve_jar` fall back to env vars and a hard-coded macOS path — pass `--java-path` / `--jar-path` on other systems. Failed `verify` attempts are archived to `workspace/history/attempt_N/` (suppress with `--no-history`).

### 3. Runtimes (`tracefix/runtime/`)
All runtimes consume the same verified workspace and share `LockStore`, `CounterStore`, `MessageStore` (in `tracefix/runtime/store.py`) plus the monitoring core (`monitoring/coord.py`, `monitor.py`, `state_tracker.py`, `correction.py`).

- **`monitoring/`** (Architecture B, OpenAI loop): agents drive themselves through pre-generated prompts and call coordination tools (`acquire_lock`, `send_message`, `receive_message`, `release_lock`, `signal_done`). `monitor.py:ProtocolMonitor` validates every op against the IR topology whitelist; `state_tracker.py:StateTracker` validates against the per-agent state machine. On an out-of-order op, `coord.py` blocks it and returns the legal next actions (`correction.py`); after `CORRECTION_CAP` unrecovered tries the agent fails honestly. See `coord.py`, `agent_runner.py`, `orchestrator.py`, `state_tracker.py`, `correction.py`.
- **`sdk_adapter/`** (Architecture B, Claude Agent SDK harness): same coordination core, but each agent's loop runs via the SDK with real `Read`/`Write`/`Edit`/`Bash` builtins (custom tasks do real work). Coordination tools are a per-agent in-process MCP server; sub-agents can run on OpenAI via a LiteLLM proxy. A workspace-local `tools.json` (or none → SDK builtins) supplies the domain layer. See `dispatch.py`, `mcp_server.py`, `sdk_runner.py`, `orchestrator.py`.
- **`coordination/`** (distributed, opt-in): puts the verified coordination logic behind a network boundary — one authoritative `CoordinationService` + per-agent `CoordClient` over the same `CoordBackend` interface, so agents run as separate processes/machines. `sdk_adapter --coord-url` switches to it; blocking stays server-side.

Real-time visualization is shared across runtimes: `event_bus.py` (async pub/sub) → `live_server.py` (asyncio HTTP/SSE, zero deps) → `live_view.py` (D3 + SSE client). Static post-run HTML lives in each runtime's `visualize.py`.

### 4. Benchmarks (`benchmark/`)
48 coordination tasks = 16 scenarios × 3 difficulties (E/M/H), loaded by `loader.py:load_task(task_id)`.
- `descriptions/{id}/` — agent-visible `description.md`, `tools.json` (OpenAI function schemas with extra `agent_ids` and `can_fail` fields), `metadata.json` (canonical agent + resource IDs — authoritative naming source).
- `environments/{id}/` — `sim.py` (instantiates a `SimContext` subclass), `tools_impl.py` (dummy fallback), `checklist.json` (coordination requirements for semantic fidelity checks).
- `tools/` — `ToolRegistry` (per-agent schema filtering), `SimContext` base class (resource management, failure injection, violation logging, per-agent seeded RNG).

Scenarios 12–16 have full simulation environments with failure injection: `--difficulty 0-3` (probabilistic 0/30/60/90%) and `--scenario N` (deterministic: fail first N calls per tool per agent) are mutually exclusive.

## Pipeline Flow & Output Artifacts

```
Task description
    → ir.json (agents, resources, channels — no states)
    → Protocol.tla + Protocol.cfg          (scaffold)
    → Protocol_translated.tla              (PlusCal compiler output)
    → tlc_output.log + tlc_error.md        (TLC verdict; repair loop on FAIL)
    → states.json                          (extract-states; per-agent state machine)
    → prompts/runtime_a/{AGENT}.md  +  prompts/runtime_b/{AGENT}.md
    → summary.json                         (repair tracking)
```

The pipeline writes failed attempts to `history/attempt_N/` for debugging. `states.json` is the ground truth that all four runtimes consume.

## IR Schema (key constraints)

- **Resources**: `Lock` (mutual exclusion) or `Counter` (non-negative integer = shared resource pool — NOT loop bounds).
- **Channels**: unbounded FIFO between agents. One channel per directed (from, to) pair; `labels` distinguishes message types.
- All agent and resource IDs in `ir.json` MUST match `benchmark/descriptions/{id}/metadata.json` exactly when working from a benchmark task.

## Claude Code Skills

Two skills under `.claude/skills/` orchestrate human-in-the-loop workflows that mirror the Python pipeline (`/tla-verify-pluscal`, `/tla-prompt-gen`). When the user invokes one, follow the workflow in the skill's `SKILL.md` — it uses native Read/Write/Edit/Bash tools rather than a custom agent loop.

## Properties Verified by TLC

Every generated spec is checked for: deadlock freedom, mutual exclusion, termination, no orphan locks, channel drainage, and type invariant. TLC does **not** check business logic — only coordination safety.
