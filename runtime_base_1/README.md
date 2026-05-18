# Runtime Base 1: Group Chat Baseline

Baseline runtime where agents coordinate purely through a **broadcast group chat** — no locks, channels, or verified protocol enforcement. Used as an experimental control to measure the value of structured coordination primitives and TLA+ verification.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  RuntimeBase1                        │
│  Loads IR (agent list only), creates agents          │
└──────────┬──────────────────────────────┬───────────┘
           │                              │
    ┌──────▼──────┐                ┌──────▼──────┐
    │ AgentRunner  │   ...         │ AgentRunner  │
    │ (from B)    │               │ (from B)     │
    └──────┬──────┘                └──────┬──────┘
           │  tool calls                  │
    ┌──────▼──────────────────────────────▼──────┐
    │       ChatCoordinationContext               │
    │  send_message / receive_message / done      │
    │         ┌──────────────────┐                │
    │         │   SharedChat     │ ← broadcast    │
    │         │  (message board) │   to all agents │
    │         └──────────────────┘                │
    │  No locks. No channels. No monitor.         │
    └─────────────────────────────────────────────┘
```

**Key design**: Uses the **Chat Adapter Pattern** — `ChatCoordinationContext` duck-types runtime_B's `CoordinationContext`, enabling direct reuse of `AgentRunner` without modification. This ensures experimental fairness (same LLM client, retry logic, concurrent execution).

## Modules

| File | Purpose |
|------|---------|
| `chat_coord.py` | SharedChat (broadcast message board) + ChatCoordinationContext (adapter) |
| `prompt_gen.py` | Generate agent prompts with task + agent list + chat guidelines |
| `orchestrator.py` | RuntimeBase1: loads IR, creates chat + agents, runs concurrently |
| `cli.py` | CLI entry point |

## Coordination Tools

Agents receive only 3 tools — no locks or structured channels:

| Tool | Blocking? | Returns |
|------|-----------|---------|
| `send_message(channel_id="group_chat", label, body)` | No | `sent` (broadcast to all) |
| `receive_message(channel_id="group_chat")` | 15s max | All unread messages (batch) / `timeout` |
| `signal_done()` | No | Terminates the agent |

**Design decisions:**
- Self-messages filtered out — agents never see their own messages
- Batch receive — all unread messages returned at once (not one-at-a-time)
- `acquire_lock` / `release_lock` return error (no locks in group chat)
- Agents coordinate resource access through verbal negotiation (announce → wait → act → notify)

## Usage

```bash
# Basic run
python -m runtime_base_1 run --task 3E --workspace agent_workspace/3E --verbose

# With real-time visualization
python -m runtime_base_1 run --task 3E --workspace agent_workspace/3E --live

# Sim-environment tasks with failure injection
python -m runtime_base_1 run --task 12E --workspace agent_workspace/12E \
  --difficulty 2 --seed 42

# Custom output directory
python -m runtime_base_1 run --task 3E --workspace agent_workspace/3E \
  --output experiments/results --no-open-html
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--task` | (required) | Task ID (e.g., `3E`, `10H`) |
| `--workspace` | — | Workspace path |
| `--experiment` | — | Experiment name (derives workspace) |
| `--model` | `gpt-5-mini` | LLM model |
| `--timeout` | `180` | Global timeout in seconds |
| `--max-rounds` | `100` | Max LLM steps per agent |
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
runtime_B         = Structured coordination + TLA+ protocol + ProtocolMonitor
runtime_base_2    = Structured coordination + NullMonitor (no protocol)
runtime_base_1    = Natural language chat only (no primitives)  ← this runtime
```

Each removes one layer of verification, isolating its contribution to coordination quality.

## How It Differs from runtime_B

| Aspect | runtime_B | runtime_base_1 |
|--------|-----------|----------------|
| Coordination model | Structured (locks + channels) | Broadcast group chat |
| Protocol enforcement | ProtocolMonitor (whitelist) | None |
| State tracking | StateTracker (states.json) | None |
| Agent prompts | PlusCal-derived step-by-step | Task + chat guidelines |
| IR usage | Full (agents/resources/channels/states) | Agent list only |
| Resource contention | Lock acquire/release | Verbal negotiation |
