# Runtime B: Monitoring Architecture

Architecture B runtime for TLA+-verified multi-agent coordination. Agents autonomously drive themselves via pre-generated prompts, while a Monitor validates every coordination operation against the IR topology.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Orchestrator                      │
│  Loads IR + prompts, creates agents, runs concurrently│
└──────────┬──────────────────────────────┬───────────┘
           │                              │
    ┌──────▼──────┐                ┌──────▼──────┐
    │ AgentRunner  │   ...         │ AgentRunner  │
    │ (LLM loop)  │               │ (LLM loop)   │
    └──────┬──────┘                └──────┬──────┘
           │  tool calls                  │
    ┌──────▼──────────────────────────────▼──────┐
    │          CoordinationContext                │
    │  acquire_lock / release_lock / send / recv  │
    │         ┌──────────────┐                    │
    │         │   Monitor    │ ← validates every  │
    │         │  (whitelist) │   operation         │
    │         └──────────────┘                    │
    │  LockStore  CounterStore  MessageStore      │
    └─────────────────────────────────────────────┘
```

**Key difference from Architecture A**: In Arch A, the runtime drives agents via state machine lookup — agents are unaware of locks/channels. In Arch B, agents drive themselves via PlusCal-derived prompts and call coordination tools directly. The Monitor only validates, never controls.

## Modules

| File | Purpose |
|------|---------|
| `monitor.py` | ProtocolMonitor: validates operations against IR topology whitelists |
| `coord.py` | CoordinationContext: shared state + 4 async coordination operations |
| `agent_runner.py` | Per-agent LLM function-calling loop with trace recording |
| `orchestrator.py` | Loads workspace config, creates agents, runs concurrently |
| `cli.py` | CLI entry point |
| `event_bus.py` | Async event bus for real-time visualization (SSE broadcast) |
| `live_server.py` | Lightweight asyncio HTTP/SSE server (zero dependencies) |
| `live_view.py` | Real-time visualization HTML template (D3 graph + SSE client) |
| `visualize.py` | Static post-run HTML visualization (`--save-html`) |

## Coordination Tools

Every agent receives 5 coordination tools via OpenAI function calling:

| Tool | Blocking? | Returns |
|------|-----------|---------|
| `acquire_lock(lock_id)` | No | `acquired` / `busy` / `already_held` |
| `release_lock(lock_id)` | No | `released` |
| `send_message(channel_id, label)` | No | `sent` |
| `receive_message(channel_id)` | 30s max | `received` + label / `timeout` |
| `signal_done()` | No | terminates the agent |

`acquire_lock` / `release_lock` handle both Lock and Counter resources transparently:
- **Lock**: mutual exclusion (one holder at a time)
- **Counter**: counting semaphore (decrement on acquire, increment on release)

## Usage

```bash
# Basic run (HTML opens in browser by default)
python -m tracefix.runtime.monitoring run --task 10H --workspace agent_workspace/10H --verbose

# With real-time visualization (browser opens during execution)
python -m tracefix.runtime.monitoring run --task 10H --workspace agent_workspace/10H --live --verbose

# Suppress auto-open of HTML after run
python -m tracefix.runtime.monitoring run --task 10H --workspace agent_workspace/10H --no-open-html

# Sim-environment tasks with failure injection
python -m tracefix.runtime.monitoring run --task 12E --workspace agent_workspace/12E --difficulty 2 --seed 42
python -m tracefix.runtime.monitoring run --task 16M --workspace agent_workspace/16M --scenario 2 --tool-time 0.5
python -m tracefix.runtime.monitoring run --task 13H --workspace agent_workspace/13H --difficulty 3 --seed 123
```

### CLI Options

**General options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--task` | (required) | Task ID (e.g., `10H`, `3E`) |
| `--workspace` | (required) | Workspace path (e.g., `agent_workspace/10H`) |
| `--model` | `gpt-5-mini` | LLM model |
| `--timeout` | `180` | Global timeout in seconds |
| `--verbose` | off | Print per-agent debug info |
| `--live` | off | Open real-time visualization in browser during execution |
| `--no-open-html` | off | Don't open `run_trace.html` in browser after run (HTML is always saved) |

**Simulation parameters** (only effective for tasks with a sim environment, i.e. scenarios 12–16):

| Flag | Default | Description |
|------|---------|-------------|
| `--difficulty` | `1` | Difficulty level: `0` / `1` / `2` / `3` |
| `--scenario` | — | Deterministic retry depth (integer) |
| `--tool-time` | — | Delay multiplier for domain tools (float) |
| `--seed` | — | Random seed for reproducible sim behavior (integer) |

`--difficulty` and `--scenario` are **mutually exclusive** — both control decision-point failure injection but via different mechanisms. `--difficulty` defaults to `1` (medium) so failure injection is always active unless overridden by `--scenario`. `--tool-time` and `--seed` are orthogonal and can be combined with either.

#### `--difficulty`

Integer (0–3) that maps to a probabilistic failure rate for all decision-point tools (tools whose outcome determines a branch in the protocol, e.g. review → approve/revise, test → pass/fail). **Default: 1**.

| Level | Name | Fail Rate | Meaning |
|-------|------|-----------|---------|
| `0` | easy | 0.0 | No injected failures — all decisions succeed on the first try |
| `1` | medium | 0.3 | 30% chance each decision-point tool returns the failure branch |
| `2` | hard | 0.6 | 60% failure — agents must retry frequently |
| `3` | nightmare | 0.9 | 90% failure — nearly every decision fails, maximum retry stress |

Example: `--difficulty 2` makes `review_code` return "revise" 60% of the time instead of "approve".

#### `--scenario`

Deterministic retry depth. Each decision-point tool fails on the first N calls (per tool per agent), then succeeds on call N+1. This gives a predictable, reproducible failure pattern independent of randomness.

- `--scenario 0` — no failures (same as `--difficulty 0`)
- `--scenario 1` — every decision fails once then passes (agents must retry exactly once)
- `--scenario 2` — every decision fails twice then passes
- `--scenario 3` — three failures before success, etc.

This is useful for testing whether agents handle retries correctly without the noise of probabilistic failure.

#### `--tool-time`

Multiplier applied to all domain tool delays (the simulated processing time returned by each sim tool, e.g. compile duration, test duration).

- `--tool-time 0` — instant execution, no `asyncio.sleep` (fastest runs)
- `--tool-time 1` — default delays as defined by each sim class (e.g. 0.5–2.0s for compile)
- `--tool-time 2` — double all delays (stress-test timeout handling and concurrent contention)
- `--tool-time 0.5` — halve delays (faster runs while still exercising async boundaries)

When omitted, the sim's built-in delays apply unchanged (equivalent to `--tool-time 1`).

#### `--seed`

Integer seed for reproducible sim-layer randomness. Controls both failure injection coin flips (from `--difficulty`) and tool delay jitter. Each agent gets a deterministic per-agent RNG derived from `seed ^ hash(agent_id)`, so:

- Different agents get different random sequences (no correlation)
- Re-running with the same `--seed` reproduces the same failure/delay pattern
- Without `--seed`, each run uses fresh unseeded randomness

Example: `--seed 42 --difficulty 2` produces the same failure sequence every time.

## Real-Time Visualization (`--live`)

When `--live` is enabled, the orchestrator starts an HTTP/SSE server at `http://127.0.0.1:8765` and opens a browser automatically. The page shows:

```
┌─────────────┐    emit()     ┌──────────┐    SSE stream    ┌─────────┐
│ AgentRunner │ ──────────→   │ EventBus │ ──────────────→  │ Browser │
│ (asyncio)   │               │ (async Q)│                  │  (D3 +  │
└─────────────┘               └──────────┘                  │  SSE)   │
                                  ↑                         └─────────┘
┌─────────────┐    emit()        │       GET /        ┌──────────────┐
│ Orchestrator│ ─────────────────┘    ←──────────     │ HTTP Server  │
│             │                       GET /api/events  │ (asyncio TCP)│
└─────────────┘                       GET /api/ir      └──────────────┘
```

### Features

- **Force-directed D3 graph**: agent nodes, resource nodes, and channel links
- **Agent status animation**: idle (gray) → LLM busy (blue pulse) → completed (green) / error (red) / timeout (orange)
- **Message beam particles**: animated SVG circles traveling along channel links on send/receive
- **Lock link highlighting**: resource links flash on acquire/release
- **Trace panel**: per-agent tool call log with auto-scroll, filterable by agent
- **Resource panel**: shows current lock holder in real-time

### SSE Event Types

| Event | Data | UI Update |
|-------|------|-----------|
| `run.start` | `{agents, channels, resources}` | Initialize graph + panels |
| `agent.llm_start` | `{agent_id, round}` | Node pulse (blue, LLM thinking) |
| `agent.tool_call` | `{agent_id, round, tool_name, arguments, result, elapsed}` | Append trace + beam animation |
| `agent.done` | `{agent_id, status, steps, duration}` | Node color: green/red/orange |
| `run.done` | `{success, duration, error}` | Header final status |

### Implementation

Zero external dependencies — uses Python `asyncio.start_server` for the HTTP/SSE server, reusing the same event loop as agent execution. The EventBus broadcasts events to all SSE subscribers via per-connection `asyncio.Queue` (max 256 events buffered).

## Workspace Layout

The orchestrator reads from the `--workspace` directory:

```
agent_workspace/10H/
├── ir.json                  # IR topology (agents, resources, channels)
├── Protocol.tla             # TLA+ spec (for reference)
├── Protocol_translated.tla  # Translated TLA+ (for reference)
├── Protocol.cfg             # TLC config (for reference)
├── prompts/
│   ├── builder_a.md         # Pre-generated agent prompt
│   ├── builder_b.md
│   ├── validator.md
│   └── ...
├── summary.json             # Verification summary
└── run_trace.html           # Static visualization (--save-html output)
```

Domain tools are loaded from `benchmark/descriptions/{task_id}/tools.json`.

## Output

Every run produces a trace showing each agent's tool calls:

```
=== RuntimeB Result ===
SUCCESS in 19.7s
  builder_a: 17 tool calls, 12.0s
  builder_b: 26 tool calls, 18.9s
  builder_d: 13 tool calls, 8.6s
  validator: 13 tool calls, 16.1s
  integrator: 6 tool calls, 19.6s

=== Tool Call Trace ===
--- builder_d (completed, 13 steps, 8.6s) ---
  R01 acquire_lock({"lock_id": "build_slots"}) → acquired [0.0s]
  R02 acquire_lock({"lock_id": "api_types"}) → acquired [0.0s]
  R03 compile_module({"module_name": "Module D"}) → ok [0.1s]
  R04 release_lock({"lock_id": "build_slots"}) → released [0.0s]
  R05 send_message({"channel_id": "to_val", "label": "req_d"}) → sent [0.0s]
  R06 receive_message({"channel_id": "val_to_d"}) → received label="pass" [0.7s]
  R10 signal_done({}) → done [0.0s]
```

## Safety Design

Three layers prevent infinite resource consumption:

1. **TLA+ verification** (design time): Protocol is deadlock-free
2. **ProtocolMonitor** (runtime): Every operation validated against IR topology
3. **Budget limits** (runtime): `max_rounds=50` per agent + global `--timeout`

In LLM MAS, traditional deadlock/livelock both manifest as the same symptom: agents fail to complete within budget. Non-blocking `acquire_lock` and timeout-based `receive_message` ensure no permanent blocking.

## Tests

```bash
python -m pytest tracefix.runtime.monitoring/tests/ -v   # 45 tests
```

- `test_monitor.py` — whitelist validation (valid + invalid operations)
- `test_coord.py` — lock contention, counter semaphore, channel FIFO, timeout
