# Runtime A: Enforcement Architecture

Architecture A runtime for TLA+-verified multi-agent coordination. The runtime mediator structurally prevents coordination violations — agents are unaware of locks and channels. The engine manages all coordination operations, calling the LLM only at decision points and business-logic states.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Runtime Engine                       │
│  Guard check → Effect apply → Wake dependents            │
│  (atomic: no await between check and mutate)             │
└──────┬──────────────────────────────────┬───────────────┘
       │                                  │
┌──────▼──────┐                    ┌──────▼──────┐
│ AgentRunner  │   ...             │ AgentRunner  │
│ (per-agent)  │                   │ (per-agent)  │
│ sleep/wake   │                   │ sleep/wake   │
└──────┬──────┘                    └──────┬──────┘
       │  policy.choose_action()          │
┌──────▼──────────────────────────────────▼──────┐
│              Shared Stores                      │
│  LockStore   CounterStore   MessageStore        │
│  (sync-only, atomicity via cooperative sched)   │
└─────────────────────────────────────────────────┘
```

**Key difference from Architecture B**: In Arch A, the engine drives agents via state machine lookup — agents are unaware of locks/channels. Coordination states (acquire/send/receive/release) auto-advance without calling the LLM. In Arch B, agents drive themselves via prompts and call coordination tools directly.

## Modules

| File | Purpose |
|------|---------|
| `engine.py` | Runtime orchestrator: guard checking, effect application, concurrent agent execution |
| `store.py` | LockStore, CounterStore, MessageStore — shared coordination primitives (reused by tracefix.runtime.monitoring) |
| `policy.py` | AgentPolicy protocol + RandomPolicy for pluggable decision-point strategy |
| `topology.py` | IR parsing, topology analysis, communication adjacency, resource contention |
| `llm_policy.py` | Continuous LLM conversation loop per agent (AsyncOpenAI, recv-context filtering) |
| `loader.py` | Task loading from workspace: `ir.json` + `states.json` + per-agent prompts |
| `cli.py` | CLI entry point |
| `visualize.py` | Static post-run HTML visualization (D3 topology + trace timeline) |
| `live_view.py` | Real-time visualization HTML template (D3 graph + SSE client) |
| `event_bus.py` | Async event bus for real-time visualization (SSE broadcast) |
| `live_server.py` | Lightweight asyncio HTTP/SSE server (zero dependencies) |
| `result_saver.py` | Serialize RunResult + traces to `run_result.json` |

## State Transition Classification

The engine classifies each agent state and handles it accordingly:

```
Current State → Enabled Actions
    ├─ 0 actions  → TERMINAL (agent done)
    ├─ 1 action
    │  ├─ has guard/effect → AUTO (engine chains, skips LLM)
    │  └─ no guard/effect → BUSINESS (LLM does domain work)
    └─ >1 actions → DECISION (LLM chooses)
```

**Auto-advance optimization**: Single coordination actions (acquire/send/receive/release) execute without LLM calls and chain automatically, reducing LLM calls from ~30 to ~7–13 per task.

## Usage

```bash
# Visualize IR topology as interactive HTML
python -m tracefix.runtime.enforcement viz /path/to/ir.json -o output.html --title "My Protocol"

# Run with random policy (baseline, no LLM)
python -m tracefix.runtime.enforcement run /path/to/ir.json --seed 42 --timeout 5 -q

# Run with LLM policy
python -m tracefix.runtime.enforcement run --task agent_workspace/3E \
  --llm --model gpt-4.1-mini --verbose --timeout 10

# Real-time visualization in browser
python -m tracefix.runtime.enforcement run --task agent_workspace/3E --llm --live --port 8765

# Sim-environment tasks with failure injection
python -m tracefix.runtime.enforcement run --task agent_workspace/12H --difficulty 2 --llm
python -m tracefix.runtime.enforcement run --task agent_workspace/4M --scenario 5 --llm
python -m tracefix.runtime.enforcement run --task agent_workspace/5H --tool-time 2.0 --llm

# Custom output, quiet mode
python -m tracefix.runtime.enforcement run --task agent_workspace/3E --output /tmp/results/ \
  --llm --quiet --no-open-html
```

### CLI Options

**General options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--task` | — | Task directory (e.g., `agent_workspace/3E`) |
| `--llm` | off | Use LLM policy (otherwise RandomPolicy) |
| `--model` | `gpt-4.1-mini` | LLM model |
| `--timeout` | `5` | Global timeout in seconds |
| `--seed` | — | Random seed for deterministic runs |
| `--verbose` | off | Print per-agent debug info |
| `--live` | off | Open real-time visualization in browser |
| `--no-open-html` | off | Don't auto-open HTML after run |

**Simulation parameters** (scenarios 12–16):

| Flag | Default | Description |
|------|---------|-------------|
| `--difficulty` | `1` | Failure rate: `0`=0%, `1`=30%, `2`=60%, `3`=90% |
| `--scenario` | — | Deterministic retry depth (mutually exclusive with `--difficulty`) |
| `--tool-time` | — | Delay multiplier for domain tools |
| `--seed` | — | Random seed for reproducible sim behavior |

## Workspace Layout

```
agent_workspace/3E/
├── ir.json                  # IR topology
├── states.json              # Extracted state machine (from tla-verify-pluscal)
├── Protocol.tla             # TLA+ spec (reference)
├── Protocol.cfg             # TLC config (reference)
├── prompts/
│   └── runtime_a/
│       ├── RESEARCHER_A.md  # Pre-generated agent prompt
│       ├── RESEARCHER_B.md
│       └── EDITOR.md
└── results/
    └── tracefix.runtime.enforcement/
        └── <timestamp>/
            ├── run_result.json
            └── run_trace.html
```

## Safety Design

Coordination violations are **structurally impossible** — the engine mediates all operations:

1. **TLA+ verification** (design time): Protocol is deadlock-free
2. **Engine enforcement** (runtime): Guards checked before effects applied; agents never touch stores directly
3. **Recv-context filtering**: Deterministic filtering prevents hub-and-spoke routing errors
4. **Budget limits** (runtime): Global `--timeout` + per-agent max steps

## Tests

```bash
python -m pytest tracefix.runtime.enforcement/tests/ -v
```

- `test_engine.py` — Protocol execution (3E, 1H), determinism, trace validity
- `test_communication.py` — Store primitives: MessageStore, LockStore, CounterStore
- `test_topology.py` — IR parsing and topology analysis
- `test_loader.py` — Task loading (ir.json + states.json)
- `test_llm_policy.py` — LLM decision loop
- `test_live.py` — Live server routes
