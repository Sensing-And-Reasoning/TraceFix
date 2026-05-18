# Runtime Base 2: Null Monitor Baseline

Baseline runtime with the **same coordination primitives** as tracefix.runtime.monitoring (locks, channels, counters) but **no protocol enforcement** — the NullMonitor validates only that resources/channels exist, not that the correct agent is using them. Agents receive generic topology hints instead of PlusCal-derived step-by-step instructions.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   RuntimeBase2                       │
│  Loads IR + generic prompts, creates agents          │
└──────────┬──────────────────────────────┬───────────┘
           │                              │
    ┌──────▼──────┐                ┌──────▼──────┐
    │ AgentRunner  │   ...         │ AgentRunner  │
    │ (from B)    │               │ (from B)     │
    └──────┬──────┘                └──────┬──────┘
           │  tool calls                  │
    ┌──────▼──────────────────────────────▼──────┐
    │          CoordinationContext                │
    │  acquire_lock / release_lock / send / recv  │
    │         ┌──────────────┐                    │
    │         │ NullMonitor  │ ← existence-only   │
    │         │ (no whitelist)│   validation       │
    │         └──────────────┘                    │
    │  LockStore  CounterStore  MessageStore      │
    └─────────────────────────────────────────────┘
```

**Key design**: Reuses tracefix.runtime.monitoring's `AgentRunner` and `CoordinationContext` directly, replacing `ProtocolMonitor` with `NullMonitor`. This isolates the value of protocol-guided prompts — agents have the same tools but must figure out the coordination strategy themselves.

## Modules

| File | Purpose |
|------|---------|
| `null_monitor.py` | NullMonitor: existence-only validation (no topology whitelists) |
| `prompt_gen.py` | Generate agent prompts with task + topology hints (no PlusCal steps) |
| `orchestrator.py` | RuntimeBase2: loads IR, creates NullMonitor + agents, runs concurrently |
| `cli.py` | CLI entry point |

## Coordination Tools

Same 7 tools as tracefix.runtime.monitoring — agents have full access to structured coordination:

| Tool | Blocking? | Returns |
|------|-----------|---------|
| `acquire_lock(lock_id)` | 30s timeout | `acquired` / `timeout` / `already_held` |
| `release_lock(lock_id)` | No | `released` |
| `send_message(channel_id, label, body?)` | No | `sent` |
| `receive_message(channel_id)` | 30s timeout | `received` + label / `timeout` |
| `poll_channels(channel_ids)` | No | First pending msg or `none` |
| `receive_any(channel_ids)` | 30s timeout | First msg from any channel / `timeout` |
| `signal_done()` | No | Terminates the agent |

**Key difference**: NullMonitor allows any agent to use any resource/channel (if it exists in the IR). Runtime_B's ProtocolMonitor enforces per-agent whitelists.

## Usage

```bash
# Basic run
python -m tracefix.runtime.baselines.null_monitor run --task 3E --workspace agent_workspace/3E --verbose

# With real-time visualization
python -m tracefix.runtime.baselines.null_monitor run --task 3E --workspace agent_workspace/3E --live

# Sim-environment tasks with failure injection
python -m tracefix.runtime.baselines.null_monitor run --task 12E --workspace agent_workspace/12E \
  --difficulty 2 --seed 42

# Custom model and timeout
python -m tracefix.runtime.baselines.null_monitor run --task 10H --workspace agent_workspace/10H \
  --model gpt-5-mini --timeout 300
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--task` | (required) | Task ID (e.g., `3E`, `10H`) |
| `--workspace` | — | Workspace path |
| `--experiment` | — | Experiment name (derives workspace) |
| `--model` | `gpt-5-mini` | LLM model |
| `--timeout` | `180` | Global timeout in seconds |
| `--max-rounds` | `50` | Max LLM steps per agent |
| `--verbose` | off | Print per-agent debug info |
| `--live` | off | Open real-time visualization |
| `--no-open-html` | off | Don't auto-open HTML |
| `--difficulty` | `1` | Failure rate: `0`=0%, `1`=30%, `2`=60%, `3`=90% |
| `--scenario` | — | Deterministic retry depth (mutually exclusive with `--difficulty`) |
| `--tool-time` | — | Delay multiplier for domain tools |
| `--seed` | — | Random seed |
| `--output` | — | Results directory root |

## Experimental Hierarchy

```
tracefix.runtime.monitoring         = Structured coordination + TLA+ protocol + ProtocolMonitor  ← full verification
tracefix.runtime.baselines.null_monitor    = Structured coordination + NullMonitor (no protocol)         ← this runtime
tracefix.runtime.baselines.shared_chat    = Natural language chat only (no primitives)
```

Each removes one layer of verification, isolating its contribution to coordination quality.

**Research question**: Can LLMs derive correct coordination from structured primitives alone, without a verified protocol guiding them?

## How It Differs from tracefix.runtime.monitoring

| Aspect | tracefix.runtime.monitoring | tracefix.runtime.baselines.null_monitor |
|--------|-----------|----------------|
| Monitor | ProtocolMonitor (topology whitelist) | NullMonitor (existence-only) |
| State tracking | StateTracker (states.json) | None |
| Agent prompts | PlusCal-derived step-by-step | Generic topology hints |
| Validation | Per-agent operation whitelists | Any agent can use any resource/channel |
| Code reuse | Foundation | Reuses AgentRunner + CoordinationContext from tracefix.runtime.monitoring |
