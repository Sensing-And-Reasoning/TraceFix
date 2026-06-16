# TraceFix Architecture & End-to-End Flow

> A visual, code-grounded walkthrough of how TraceFix turns a natural-language task
> into a **formally verified** multi-agent coordination protocol, and then runs real
> LLM agents against it without ever letting them violate that protocol.
>
> This document is for contributors and users who want the *whole picture*. Every box
> below maps to a real module; file paths are given so you can jump straight to the code.

---

## Table of contents

1. [The one-minute mental model](#1-the-one-minute-mental-model)
2. [The artifact pipeline](#2-the-artifact-pipeline)
3. [Part I — Design & Verification](#3-part-i--design--verification)
   - [3.1 Two stacked layers](#31-two-stacked-layers)
   - [3.2 The outer agentic loop](#32-the-outer-agentic-loop)
   - [3.3 The inner deterministic pipeline](#33-the-inner-deterministic-pipeline)
   - [3.4 The repair loop](#34-the-repair-loop)
   - [3.5 The human-facing CLI](#35-the-human-facing-cli)
4. [Part II — Prompt generation (Phase 5)](#4-part-ii--prompt-generation-phase-5)
5. [Part III — Runtime execution](#5-part-iii--runtime-execution)
   - [5.1 The three-plane model](#51-the-three-plane-model)
   - [5.2 The coordination core](#52-the-coordination-core)
   - [5.3 The validation pipeline (per operation)](#53-the-validation-pipeline-per-operation)
   - [5.4 Three harnesses over one core](#54-three-harnesses-over-one-core)
   - [5.5 The distributed boundary](#55-the-distributed-boundary)
   - [5.6 The mixed-harness proof](#56-the-mixed-harness-proof)
   - [5.7 Typed domain tools](#57-typed-domain-tools--real-apis-beside-the-builtins)
6. [Part IV — Benchmarks](#6-part-iv--benchmarks)
7. [Part V — The observability plane](#7-part-v--the-observability-plane)
8. [Appendix A — Artifact reference](#8-appendix-a--artifact-reference)
9. [Appendix B — Key invariants](#9-appendix-b--key-invariants)
10. [Appendix C — Directory map](#10-appendix-c--directory-map)

---

## 1. The one-minute mental model

TraceFix has two halves joined by a set of **verified artifacts**:

```mermaid
flowchart LR
    T["Task description<br/>(prose or benchmark id)"]

    subgraph DESIGN["① DESIGN &amp; VERIFY — LLM proposes, TLA+ proves"]
        direction TB
        IR["ir.json<br/>(agents · resources · channels)"]
        TLA["Protocol.tla<br/>(PlusCal)"]
        TLC{"TLC<br/>model checker"}
        ST["states.json<br/>(per-agent FSM)"]
        PR["prompts/runtime_b/*.md"]
        IR --> TLA --> TLC
        TLC -- "counterexample → repair" --> IR
        TLC -- "PASS" --> ST --> PR
    end

    subgraph RUN["② EXECUTE — real agents, can't break the protocol"]
        direction TB
        HARN["Agent harness<br/>(monitoring · sdk_adapter · opencode)"]
        CORE["Coordination CORE<br/>monitor + FSM + stores"]
        HARN <--> CORE
    end

    T --> IR
    PR --> HARN
```

- **Half ①** is *open-loop reasoning made safe*: an LLM designs the coordination
  protocol, but a model checker (TLC) exhaustively proves it is free of deadlocks,
  race conditions, and orphaned resources **before any agent runs**.
- **Half ②** is *execution that can't drift*: real LLM agents do the actual work, but
  every coordination move they make is checked against the verified protocol at
  runtime. An illegal move is blocked and the agent is handed the legal next actions.

The contract between the halves is the **artifact set** (`ir.json`, `states.json`,
`prompts/runtime_b/`). Anything that consumes these artifacts gets the same guarantees.

> **What TLC checks vs. what it doesn't.** TLC verifies *coordination safety*
> (can two agents hold the same lock? can the system deadlock? does everyone
> terminate? are all locks released and channels drained?). It does **not** check
> business-logic correctness — that is the agents' job at runtime, on the data plane.

---

## 2. The artifact pipeline

Everything downstream is a deterministic function of `ir.json`. This is the spine of
the whole system:

```mermaid
flowchart TD
    IR["ir.json<br/><i>agents, resources, channels</i>"]
    SCAF["Protocol.tla + Protocol.cfg<br/><i>PlusCal scaffold + TLC config</i>"]
    TRANS["Protocol_translated.tla<br/><i>TLA+ after pcal.trans</i>"]
    LOG["tlc_output.log<br/>tlc_error.md<br/><i>verdict / counterexample</i>"]
    STATES["states.json<br/><i>per-agent state machine</i>"]
    PROMPTS["prompts/runtime_b/{agent}.md<br/><i>per-agent workflow prompts</i>"]

    IR -- "pluscal_generator.py" --> SCAF
    SCAF -- "pluscal_compiler.py<br/>(java pcal.trans)" --> TRANS
    TRANS -- "tlc_runner.py<br/>(java tlc2.TLC)" --> LOG
    LOG -- "FAIL: trace_parser + error_formatter<br/>→ repair ir.json/Protocol.tla" --> IR
    TRANS -- "PASS: pluscal_parser.py<br/>(tree-sitter)" --> STATES
    STATES -- "Phase 5 prompt-gen" --> PROMPTS

    style IR fill:#e3f2fd,stroke:#1565c0
    style STATES fill:#e8f5e9,stroke:#2e7d32
    style PROMPTS fill:#fff3e0,stroke:#e65100
```

| Stage | Module | In → Out |
|---|---|---|
| Validate | `pipeline/pipeline/validator.py` (`schema.json`) | `ir.json` → schema + semantic OK |
| Scaffold | `pipeline/pipeline/pluscal_generator.py` | `ir.json` → `Protocol.tla` + `Protocol.cfg` |
| Translate | `pipeline/pipeline/pluscal_compiler.py` | `Protocol.tla` → `Protocol_translated.tla` (via `pcal.trans`) |
| Model-check | `pipeline/pipeline/tlc_runner.py` | `Protocol_translated.tla` + `.cfg` → `tlc_output.log` + verdict |
| Explain (on fail) | `trace_parser.py` + `error_formatter.py` | TLC counterexample → human/LLM-readable repair prompt |
| Extract | `pipeline/pipeline/pluscal_parser.py` | `Protocol_translated.tla` + `ir.json` → `states.json` |
| Prompt-gen | Phase 5 (agentic or `/tla-prompt-gen` skill) | `states.json` + `ir.json` → `prompts/runtime_b/*.md` |

The inner pipeline is **pure and deterministic** — no LLM, no randomness. Re-running it
on the same `ir.json` always yields byte-identical artifacts.

---

## 3. Part I — Design & Verification

### 3.1 Two stacked layers

The `tracefix/pipeline/` package is two layers glued together:

```mermaid
flowchart TB
    subgraph OUTER["OUTER — agentic loop (LLM-driven)  ·  tracefix/pipeline/"]
        direction TB
        LOOP["loop.py — think · act · observe"]
        CLIENT["tool_client.py — OpenAI / Anthropic / OpenRouter"]
        TOOLS["tools.py — 10 tool schemas + registry"]
        PROMPTS["prompts.py — system prompt (IR schema, anti-patterns, 2PC example)"]
        LOOP --- CLIENT
        LOOP --- TOOLS
        LOOP --- PROMPTS
    end
    subgraph INNER["INNER — deterministic compiler (no LLM)  ·  tracefix/pipeline/pipeline/"]
        direction TB
        V["validator"] --> G["pluscal_generator"] --> C["pluscal_compiler"] --> R["tlc_runner"] --> P["pluscal_parser"]
    end
    TOOLS -- "validate_ir / compile_scaffold / verify_spec / extract_states" --> INNER
```

- The **outer layer** is the autonomous agent that *writes* the protocol. It calls the
  inner pipeline through tools, reads the results, and iterates.
- The **inner layer** is the *compiler + verifier*. It has no opinions — it just
  transforms and checks.

The same inner pipeline is also reachable directly through the [CLI](#35-the-human-facing-cli)
(no LLM), so you can drive verification by hand.

### 3.2 The outer agentic loop

```mermaid
flowchart TD
    START(["python -m tracefix.pipeline<br/>--task / --benchmark / --prompt-gen-only"]) --> INIT["build LLMConfig · Workspace · AgentLoop"]
    INIT --> THINK

    subgraph TAO["think → act → observe  (loop.py, until done or max turns)"]
        direction TB
        THINK["LLM call (tool_client.chat)"]
        ACT["execute tool calls<br/>read-only ∥ parallel · mutating → sequential"]
        OBSERVE["append results · save session.json"]
        COMPRESS["context compression<br/>(summarize old turns > ~150K chars)"]
        DOOM["doom-loop detector<br/>(same tool N× → force a new strategy)"]
        THINK --> ACT --> OBSERVE --> COMPRESS --> THINK
        ACT -.-> DOOM
    end

    OBSERVE -- "no more tool calls" --> DONE(["final report · cost summary"])
```

**The 10 tools** (`tools.py`) are the agent's entire action space:

| Tool | What it does |
|---|---|
| `think` | scratchpad reasoning (no side effect) |
| `read_file` / `write_file` / `edit_file` / `list_files` | workspace file I/O |
| `load_benchmark` | pull a benchmark task's `description.md` + `tools.json` + `metadata.json` |
| `validate_ir` | run the schema + semantic validator |
| `compile_scaffold` | `ir.json` → `Protocol.tla` + `Protocol.cfg` |
| `verify_spec` | translate PlusCal + run TLC; archive failed attempts to `history/attempt_N/` |
| `extract_states` | verified TLA+ → `states.json` |

The recommended workflow encoded in the system prompt (`prompts.py`):

```mermaid
flowchart LR
    P1["Phase 1<br/>hazard analysis<br/>+ design ir.json"] --> P15["Phase 1.5<br/>coordination plan<br/>+ self-critique"]
    P15 --> P2["Phase 2<br/>write PlusCal<br/>bodies"] --> P25["Phase 2.5<br/>semantic-fidelity<br/>checklist"]
    P25 --> P3["Phase 3<br/>verify + repair<br/>(TLC)"] --> P4["Phase 4<br/>extract_states"]
    P4 --> P5["Phase 5<br/>generate prompts"]
    P3 -. "counterexample" .-> P2
```

`tool_client.py` makes the loop **provider-agnostic** — the same canonical message and
tool-call format is translated to OpenAI (Chat Completions or Responses API),
Anthropic, or OpenRouter, including reasoning effort / thinking budget and prompt
caching.

### 3.3 The inner deterministic pipeline

```mermaid
flowchart TD
    IR["ir.json"] --> VAL{"validator.py<br/>schema + semantics"}
    VAL -- invalid --> ERRV["error list → agent fixes ir.json"]
    VAL -- valid --> GEN["pluscal_generator.py"]

    GEN --> TLA["Protocol.tla (PlusCal)<br/>+ Protocol.cfg"]
    TLA --> COMP{"pluscal_compiler.py<br/>java -cp tla2tools.jar pcal.trans"}
    COMP -- parse error --> ERRC["pcal error → agent fixes PlusCal"]
    COMP -- ok --> TRANS["Protocol_translated.tla"]

    TRANS --> TLC{"tlc_runner.py<br/>java tlc2.TLC -workers auto -Xmx4g"}
    TLC -- "FAIL (deadlock / safety / error)" --> TP["trace_parser.py → error_formatter.py<br/>(counterexample → repair prompt)"]
    TLC -- "PASS (fail-closed verdict)" --> EXT["pluscal_parser.py (tree-sitter)"]
    EXT --> STATES["states.json"]

    style STATES fill:#e8f5e9,stroke:#2e7d32
```

State-space optimizations baked into the generator so TLC stays tractable:

- **One channel per directed (from, to) pair** — `labels` distinguish message types;
  the validator *rejects* duplicate edges.
- **`ChannelBound` CONSTRAINT** — caps channel length so unbounded FIFOs don't explode
  the state space.
- **Per-agent `Next` disjunction** instead of a `\E agent \in Agents` quantifier —
  skips guard evaluation for actions that can't fire for a given agent.
- **String messages**, not TLA+ records — simpler, smaller states.
- **Safety-only checking** — no fairness, no liveness temporal operators; deadlock is
  detected natively by TLC. Because liveness isn't checked, loops need not be bounded.
- **Fail-closed verdict** — `tlc_runner.py` declares success *only* on an explicit
  "Model checking completed" + "No error" token pair. Anything ambiguous is a failure,
  so an unverified spec can never be shipped.

Properties verified on every spec: **deadlock freedom · mutual exclusion · termination ·
no orphan locks · channel drainage · type invariant.**

### 3.4 The repair loop

When TLC fails, the counterexample is turned into a targeted repair prompt and fed
back to the agent. A circuit breaker prevents thrashing:

```mermaid
sequenceDiagram
    participant A as Agent loop
    participant V as verify_spec
    participant TLC as TLC
    participant F as error_formatter

    A->>V: verify_spec()
    V->>TLC: translate + model-check
    alt PASS
        TLC-->>V: 0 errors
        V-->>A: PASS + stats → proceed to extract_states
    else FAIL
        TLC-->>V: counterexample trace
        V->>F: format trace (annotated, root-cause hints)
        F-->>A: repair prompt (tlc_error.md)
        Note over A,V: archive attempt → history/attempt_N/
        A->>A: edit ir.json / Protocol.tla
        Note over V: circuit breaker — same violation 3× → abort,<br/>recommend IR redesign
    end
```

### 3.5 The human-facing CLI

The exact same inner pipeline is exposed *without any LLM* via the `tla-verify-pluscal`
entry point (`tracefix/cli/cli.py`), for scripting, CI, and the Claude Code skills:

```mermaid
flowchart LR
    INIT["init<br/>scaffold workspace/"] --> VALIDATE["validate<br/>ir.json checks"]
    VALIDATE --> SCAFFOLD["scaffold<br/>→ Protocol.tla/.cfg"]
    SCAFFOLD --> VERIFY["verify<br/>pcal.trans + TLC"]
    VERIFY --> EXTRACT["extract-states<br/>→ states.json"]
```

| Command | Inner call | Output |
|---|---|---|
| `init <name>` | — | `workspace/<name>_<timestamp>/` (a *fresh* dir each init) with `spec/ prompts/ output/` + `description.md` |
| `validate ir.json` | `validate_ir` | `VALID` / `INVALID` + errors |
| `scaffold ir.json -o ws/` | `generate_pluscal_scaffold` | `Protocol.tla` + `Protocol.cfg` |
| `verify ws/` | `translate_pluscal` + `run_tlc` | `Protocol_translated.tla`, `tlc_output.log`, `tlc_error.md` |
| `extract-states ws/` | `parse_pluscal` (tree-sitter) | `states.json` (+ `tools.json` if the PlusCal carries `[tool:]` tags) |
| `guide [topic]` | — | prints the **single-source design knowledge** (workflow · PlusCal patterns · prompt-gen) — the same files the skill and the TUI `designer` consume |

Java and the TLA+ toolchain jar resolve through a fallback chain:
`--java-path`/`--jar-path` flag → `TLA_VERIFY_JAVA`/`TLA_VERIFY_JAR` env → hard-coded
macOS Homebrew default. Failed `verify` attempts are archived to
`workspace/history/attempt_N/` (suppress with `--no-history`).

> **Design entry points & single-source knowledge.** Driving this design+verify workflow
> *interactively* has a first-choice front door: the **TraceFix TUI** (`tracefix-tui`, an
> opencode fork) whose `designer` agent runs `tla-verify-pluscal guide` and walks the user
> through it with question prompts + a plan-approval gate. The second choice is the
> `/tla-verify-pluscal` **skill** for users on their own agent harness (Claude Code, etc.).
> `tracefix design` (headless, via `opencode_adapter/design.py`) is the same workflow run
> non-interactively — kept for automation/CI/benchmarking, not promoted as a user path. All
> three read the **one** design knowledge source (the skill files), so they never drift: the
> TUI/headless pull it through `guide`, the skill reads it directly.

---

## 4. Part II — Prompt generation (Phase 5)

Phase 5 turns the verified state machine into one self-contained workflow prompt per
agent. **`states.json` is the ground truth** — every coordination call in a prompt must
map to a transition in the FSM.

```mermaid
flowchart TD
    IN["ir.json + states.json + tools.json + description.md + summary.json"]
    INV["2a · per-agent state inventory<br/>(every state_id, its actions, task, tool_hint)"]
    MAP["2b · label→step mapping table<br/>(each state appears once, in PlusCal order)"]
    PROSE["2c · prose translation<br/>acquire→'call acquire_lock', send→'call send_message', …"]
    CHECK["2d · verification checklist<br/>(all states covered? IDs exact? signal_done at the end?)"]
    OUT["prompts/runtime_b/{agent}.md"]

    IN --> INV --> MAP --> PROSE --> CHECK --> OUT
    CHECK -. "gap found" .-> PROSE
```

A generated prompt has a fixed anatomy:

```
# {agent_id} — Agent Prompt
## 1. Context            role + position in the protocol topology
## 2. Coordination       shared resources (locks/counters) + channels you send/receive
## 3. Step-by-step       numbered workflow: Coordinate lines (control) + Work lines (business)
## Critical Rules        rule #1 is always "adhere to the protocol; retry on timeout"
```

Key design points:

- **No `## Tools` section.** The runtime injects both the domain tool schemas *and* the
  coordination tool schemas separately. The prompt only references them by name.
- **Business `task` lines** come from `\* domain:` / `(* ... *)` comments in the PlusCal,
  lifted into `states.json` `task` fields. They describe *what work* happens in a state
  but never affect coordination order.
- **Control vs. business are visually split** in each step: a `Coordinate:` line (lock /
  channel op) and a `Work:` line (domain work).
- Runtime A (a coordination-free prompt variant) **was retired** — the system generates
  `runtime_b/` only.

---

## 5. Part III — Runtime execution

### 5.1 The three-plane model

This is the central idea of the runtime. Agent activity is split into three planes that
**cannot interfere** with each other:

```mermaid
flowchart TB
    subgraph CONTROL["🔒 CONTROL PLANE — verified + enforced"]
        direction TB
        C1["acquire_lock · release_lock"]
        C2["send_message · receive_message · poll_channels · receive_any"]
        C3["signal_done"]
        CNOTE["channels carry a finite LABEL only (a flag).<br/>every op checked vs. IR topology + per-agent FSM."]
    end
    subgraph DATA["📦 DATA PLANE — black box, never verified"]
        direction TB
        D1["post_content → opaque ref 'cs_N'"]
        D2["get_content(ref)"]
        D3["domain tools: Read / Write / Edit / Bash<br/>· typed tools (MCP) · benchmark simulators"]
        DNOTE["business content lives here (claim-check).<br/>bypasses the monitor entirely."]
    end
    subgraph OBS["📡 OBSERVABILITY PLANE — telemetry, never gates"]
        direction TB
        O1["report_progress(label) → beacons"]
        O2["business phases (auto-derived from skip states)"]
        ONOTE["pure pub/sub for the live view.<br/>can be disabled with zero semantic change."]
    end

    CONTROL -. "a content-carrying label may reference a ref" .-> DATA
```

The load-bearing rule is **SOLE-MEDIATION**:

> Coordination state `S = (locks, counters, channel-FIFOs, FSM positions, done-set)` can
> *only* be mutated by a monitored, content-blind, FSM-gated control-plane op. **Business
> content can never *cause* a coordination transition.**

This is why content is deliberately pushed to the data plane (the *claim-check*
pattern): a message on a channel carries an opaque ref like `cs_7`, not the content
itself. The verified protocol reasons about *labels* (`accept`, `revise`, `submit`); the
actual revision text rides the data plane where TLC never has to see it. The control
plane and the verified spec stay in lock-step.

### 5.2 The coordination core

Every harness reuses this core **unchanged** (`tracefix/runtime/store.py` +
`tracefix/runtime/monitoring/`):

```mermaid
flowchart TB
    subgraph CTX["CoordinationContext  (the hub · coord.py)"]
        direction TB
        subgraph STORES["Stores — store.py"]
            LS["LockStore<br/>lock → holder"]
            CS["CounterStore<br/>counter → slots"]
            MS["MessageStore<br/>channel → FIFO of StoredMessage(label, ref)"]
            CV["ConversationStore<br/>ref → ContentEntry (data plane)"]
        end
        MON["ProtocolMonitor — monitor.py<br/>IR topology whitelist<br/>(who may send/recv on which channel + valid labels)"]
        TRK["StateTracker — state_tracker.py<br/>per-agent FSM from states.json<br/>(legal next actions · can_terminate · guards)"]
        CORR["correction loop — correction.py<br/>CORRECTION_CAP = 3"]
    end

    AG["agent tool call"] --> CTX
    MON -. "topology check" .-> CTX
    TRK -. "FSM check" .-> CTX
    CTX -. "out-of-order → legal actions" .-> CORR --> AG
```

- **`ProtocolMonitor`** answers *static* questions from `ir.json`: may this agent send on
  this channel? is this label valid here? does this lock exist?
- **`StateTracker`** answers *dynamic* questions from `states.json`: given where this
  agent is in its FSM, is this op a legal next step? can it terminate now?
- **`correction.py`** turns a rejection into a teachable moment — it hands the agent the
  legal next actions. After `CORRECTION_CAP` (3) unrecovered tries at the same state, the
  run **fails honestly** rather than looping forever.

### 5.3 The validation pipeline (per operation)

Every control-plane op runs the same gauntlet, in this order:

```mermaid
sequenceDiagram
    participant Agent
    participant Disp as Dispatcher
    participant Mon as ProtocolMonitor
    participant Trk as StateTracker
    participant Store

    Agent->>Disp: acquire_lock / send_message / …
    Disp->>Mon: validate_* (IR topology whitelist)
    alt topology illegal
        Mon-->>Agent: ProtocolViolation (hard reject)
    else topology OK
        Disp->>Trk: _guard via check_op (FSM, read-only snapshot)
        alt out-of-order
            Trk-->>Disp: StateGuidanceError(legal_actions)
            Disp-->>Agent: corrective result (here are your legal moves)
        else legal
            Disp->>Store: apply effect (acquire / append / pop)
            Disp->>Trk: _track_and_emit (advance FSM, under per-agent lock)
            Trk-->>Agent: success {status: …}
        end
    end
```

The three hardening fixes that close real holes (each backed by a regression test):

| Fix | Hole | Guard |
|---|---|---|
| **H1** | `send_message` could smuggle a free-form `body`, bypassing the data/control split | `body` removed from the base schema; channels are flag-only. A `ref` is allowed *only* on declared `content_labels` (default-closed), and those labels *require* a ref. |
| **H2** | `release_lock` didn't check ownership — a non-holder could free someone else's lock, breaking mutual exclusion | owner check *before* the effect: only the current holder may release. |
| **H3** | `signal_done` could fire while protocol obligations remained, stranding peers | `can_terminate()` walks the FSM (skip chains + guards) to confirm a terminal state is reachable before allowing done. |

### 5.4 Three harnesses over one core

The agent *loop* is pluggable; the verified *core* is not. Each harness translates its
native tool calls into the same `CoordToolDispatcher` → `CoordinationContext` path:

```mermaid
flowchart TB
    subgraph H_MON["monitoring/  (OpenAI loop)"]
        M1["agent_runner.py<br/>OpenAI function-calling loop"]
    end
    subgraph H_SDK["sdk_adapter/  (Claude Agent SDK)"]
        S1["sdk_runner.py<br/>real Read/Write/Edit/Bash builtins"]
        S2["mcp_server.py<br/>per-agent in-process MCP"]
        S1 --- S2
    end
    subgraph H_OC["opencode_adapter/  (external opencode binary)"]
        O1["driver.py<br/>spawns 'opencode run'"]
        O2["coord_mcp/server.py<br/>per-agent stdio MCP"]
        O1 --- O2
    end

    DISP["CoordToolDispatcher<br/>(per agent, agent_id bound)"]
    CORE["CoordinationContext<br/>monitor + FSM + stores"]

    M1 --> DISP
    S2 --> DISP
    O2 --> DISP
    DISP --> CORE

    style CORE fill:#e8f5e9,stroke:#2e7d32
```

| Harness | Agent loop | Domain work | Coordination transport |
|---|---|---|---|
| **`monitoring/`** | built-in OpenAI loop | benchmark simulators (`SimContext`) | direct in-process calls |
| **`sdk_adapter/`** | Claude Agent SDK `query()` | **real** `Read`/`Write`/`Edit`/`Bash` (or `tools.json`) | per-agent **in-process** MCP server |
| **`opencode_adapter/`** | external `opencode` binary (no source mods) | opencode's builtins | per-agent **stdio** MCP (`coord_mcp`) → `CoordClient` → central service |

What stays identical across all three: the coordination tool schemas
(`COORD_TOOL_SCHEMAS`), the monitor, the FSM tracker, the correction loop, the
three-plane split, and the per-agent prompts. Swapping the harness changes *who runs the
agent*, never *what the protocol allows*.

> **`opencode_adapter/` is the default harness** (what `tracefix run` and the TUI use).
> **`sdk_adapter/`** also does real work with real file/shell tools. **`monitoring/` is the
> benchmark/eval harness** (deterministic simulators, failure injection, cost tracking).

### 5.5 The distributed boundary

`coordination/` puts the verified core behind a network seam so agents can be separate
processes. The trick: the verified logic runs **verbatim** inside one authoritative
service; blocking stays server-side.

```mermaid
flowchart LR
    subgraph NODE_A["agent process A"]
        DA["CoordToolDispatcher"] --> CCA["CoordClient"]
    end
    subgraph NODE_B["agent process B"]
        DB["CoordToolDispatcher"] --> CCB["CoordClient"]
    end
    subgraph SERVICE["CoordinationService (one authority)"]
        SVC["HTTP /rpc · /monitoring · /health"]
        CORE["CoordinationContext<br/>(unchanged: monitor + FSM + stores)"]
        SVC --> CORE
    end
    CCA -- "POST /rpc (JSON)" --> SVC
    CCB -- "POST /rpc (JSON)" --> SVC

    style CORE fill:#e8f5e9,stroke:#2e7d32
```

- **`CoordBackend`** (`backend.py`) is the seam: both the in-process
  `CoordinationContext` and the remote `CoordClient` satisfy the same interface, so the
  dispatcher doesn't know or care which one it's holding.
- **Blocking is transparent**: a remote `receive` / `acquire_lock` simply doesn't return
  its HTTP response until the server-side `asyncio.Condition` fires. No cross-node
  signaling needed.
- This is the **IPC backbone the opencode harness uses on every run** (its subprocesses
  reach the in-process service over loopback). `sdk_adapter --coord-url` switches to it
  too.
- **Full parity over the wire.** The control plane, the data plane
  (`post_content`/`get_content`, served from the one authoritative `ConversationStore` so a
  `ref` posted on one node resolves on another), and the `signal_done` FSM gate all route
  through the service — the distributed path enforces exactly what in-process does. Each
  agent also carries a per-agent capability **token** (`X-Tracefix-Token`), so a process
  that can reach the loopback port (e.g. an opencode agent with Bash) cannot forge
  coordination ops as a *different* agent.
- **Phase-1 scope (loopback only).** The service binds `127.0.0.1`, so all agents run on one
  machine; cross-machine deployment (shared artifact store, TLS, reconnect) is future work.

### 5.6 The mixed-harness proof

`mixed_run.py` is the falsifiable claim that the core really is harness-agnostic: it runs
*some* agents on opencode and *others* on the Claude SDK, against **one** service and
**one** output directory. Channels that cross the harness boundary prove the FSM treats
every agent identically.

```mermaid
flowchart TB
    SVC["one CoordinationService + shared output/"]
    subgraph OC["OpencodeOrchestrator"]
        A1["agent 1 (opencode)"]
        A2["agent 2 (opencode)"]
    end
    subgraph SDK["SdkOrchestrator"]
        A3["agent 3 (SDK)"]
        A4["agent 4 (SDK)"]
    end
    A1 & A2 & A3 & A4 -- "same coord_url" --> SVC
    A2 -. "channel crosses the harness boundary" .-> A3
```

### 5.7 Typed domain tools — real APIs beside the builtins

By default an agent's domain work uses the harness builtins (`Read`/`Write`/`Edit`/`Bash`)
or a benchmark simulator. But a design can give a *specific* agent a **typed domain tool**
— a named function with a real implementation — by tagging the PlusCal step:

```
\* domain: charge the customer [tool: charge_payment(amount: number) -> {ok, txn_id}; impl: external]
```

`extract-states` lifts each tag into a workspace `tools.json` (JSON-Schema + per-tool
`agent_ids` = the process the tag lives in) plus an implementation stub, and the runtime
exposes each typed tool **only to its owning agent** over MCP:

```mermaid
flowchart LR
    TAG["PlusCal step:<br/>domain: … [tool: name(args) -&gt; ret; impl: external · local]"]
    TJ["tools.json (schema + agent_ids)<br/>+ impl stub"]
    LOC["impl: local → domain_mcp/<br/>(Python impls, in-process MCP)"]
    EXT["impl: external → config_gen.domain_wiring<br/>(attaches an external MCP server)"]
    AG["only the owning agent sees the tool"]
    TAG -- "extract-states" --> TJ
    TJ -- "impl: local" --> LOC --> AG
    TJ -- "impl: external" --> EXT --> AG
```

So one run mixes **builtin collaboration** (agents editing shared files under the verified
locks) with **real typed API calls** (an agent invoking an external service) — and the
coordination protocol is identical either way: typed tools live on the **data plane** and
are never seen by the monitor. A hand-written workspace `tools.json` works the same way;
benchmark tasks ship one. Plain `\* domain:` work (no tag) just runs on the builtins.

---

## 6. Part IV — Benchmarks

`benchmark/` ships two tiers. The **fully-specified tier** is **48 coordination tasks =
16 scenarios × 3 difficulties (E/M/H)** — descriptions enumerate the agents, resources, and
communication, so they measure *extraction + compilation + verification + repair* against
canonical IDs.

```mermaid
flowchart TB
    LOADER["loader.py · load_task('12E')"]
    subgraph DESC["descriptions/{id}/ — agent-visible"]
        DMD["description.md<br/>(narrative: agents, resources, workflow, goal)"]
        DTOOLS["tools.json<br/>(OpenAI fn schemas + agent_ids + can_fail)"]
        DMETA["metadata.json<br/>⭐ canonical agent + resource IDs"]
    end
    subgraph ENV["environments/{id}/ — simulation (scenarios 12–16)"]
        SIM["sim.py → SimContext subclass"]
        IMPL["tools_impl.py (dummy fallback)"]
        CHK["checklist.json (coordination requirements)"]
    end
    REG["ToolRegistry<br/>(per-agent schema filtering · dispatch to sim)"]

    LOADER --> DESC
    LOADER --> CHK
    DTOOLS --> REG
    SIM --> REG
    DMETA -. "authoritative naming" .-> IRNOTE["ir.json agent/resource IDs<br/>MUST match metadata.json exactly"]

    style DMETA fill:#fff3e0,stroke:#e65100
    style IRNOTE fill:#fff3e0,stroke:#e65100
```

- **`metadata.json` is the single source of truth for naming.** Agent and resource IDs in
  `ir.json` must match it *exactly* (case-sensitive) — the registry filters tools by
  agent ID and the simulator tracks resources by ID, so a mismatch silently breaks both.
- **`ToolRegistry`** filters the tool schema per agent (`agent_ids`) and strips the extra
  `agent_ids` / `can_fail` fields before handing schemas to the LLM.
- **`SimContext`** (base class) provides resource management, per-agent seeded RNG,
  violation logging, and **failure injection**. Scenarios 12–16 have full simulators;
  two mutually-exclusive injection modes:
  - `--difficulty 0-3` → probabilistic failure `{0%, 30%, 60%, 90%}` on decision tools;
  - `--scenario N` → deterministic: fail the first N calls per tool per agent.
- Scenarios **1–11 are coordination-only** (descriptions + checklist, no simulator).

The **narrative tier** (`benchmark/underspecified/{id}/` — `description.md` + `meta.json`)
measures the *design* capability instead: 6 scenarios rewritten as unscaffolded prose, with
**no** agent/resource enumeration, so the designer must derive the topology itself. It is
scored property-based by `python -m benchmark.underspec_eval --task <id>`: TLC PASS
(`spec/summary.json`) + structural assumptions recorded in `plan.md` under `## Assumptions`
+ every requirement on the parent scenario's `checklist.json` satisfied, judged by an LLM
that is **name-agnostic** (the designer picks its own IDs). `meta.json` links each task to
its fully-specified parent; `benchmark/tests/test_underspecified.py` guards that no
scaffolding or canonical IDs leak back into the prose.

---

## 7. Part V — The observability plane

A pure-telemetry layer that renders runs live in the browser and **never** gates
coordination — if it crashes, the protocol is unaffected.

```mermaid
flowchart LR
    subgraph SOURCES["emitters (in the runtime)"]
        CO["CoordinationContext<br/>state.transition · agent.phase · state.violation"]
        AR["AgentRunner<br/>llm_start/end · tool_call · agent.done"]
        RP["report_progress()<br/>agent.progress (beacons)"]
    end
    EB["event_bus.py<br/>async pub/sub (per-subscriber queue, maxsize 256)"]
    LS["live_server.py<br/>raw asyncio HTTP + SSE (zero deps)"]
    LV["live_view.py<br/>D3 force graph + EventSource client"]
    BR(["browser — animated topology,<br/>lock beams, live trace"])

    CO & AR & RP --> EB --> LS -- "GET /api/events (SSE)" --> LV --> BR
```

- **Business phases** are *auto-derived*: when an agent sits in a no-op skip state (doing
  domain work), the `StateTracker` records it as the agent's current phase. Phases are
  never in `states.json` and never verified — they're a UI convenience.
- **Beacons** (`report_progress`) deliberately bypass `_track_and_emit` — they append to a
  `beacons` list and emit an event, touching neither monitor, FSM, nor stores.
- Toggled per-harness with `--live`. No `--live` → `event_bus = None` and every code path
  behaves identically, minus the SSE emissions. There's also a **static** post-run HTML
  renderer (`visualize.py`) that bakes the full trace into a standalone file.

---

## 8. Appendix A — Artifact reference

| Artifact | Produced by | Consumed by | Role |
|---|---|---|---|
| `description.md` / `tools.json` | task author / benchmark | agentic loop, prompt-gen, runtime | the task + domain tools |
| `ir.json` | agentic loop / `init` | everything downstream | coordination topology (agents, resources, channels) |
| `Protocol.tla` + `Protocol.cfg` | `pluscal_generator` | `pcal.trans`, TLC | PlusCal spec + TLC config |
| `Protocol_translated.tla` | `pcal.trans` | TLC, `pluscal_parser` | translated TLA+ |
| `tlc_output.log` / `tlc_error.md` | `tlc_runner` / `error_formatter` | agent (repair), humans | verdict / counterexample |
| `states.json` | `pluscal_parser` | prompt-gen, `StateTracker` | **per-agent FSM — the runtime ground truth** |
| `summary.json` | verify loop | prompt-gen | repair tracking (boosts Critical Rules) |
| `prompts/runtime_b/{agent}.md` | Phase 5 | all harnesses | per-agent workflow prompt |
| `output/shared/` | agents at runtime | other agents | the data plane: handoff/coordinated files (every agent's cwd) |
| `output/<agent>/` | one agent at runtime | itself | that agent's private scratch (its own tests, temp, intermediate work) |
| `run_result.json` / `run_trace.html` | `result_saver` / `visualize` | analysis, dashboards | run snapshot + visualization |

---

## 9. Appendix B — Key invariants

1. **Sole mediation** — coordination state changes *only* through a monitored,
   FSM-gated, content-blind control-plane op.
2. **Content can never cause a transition** — `post_content`/`get_content` bypass the
   monitor entirely; channels carry labels (+ opaque refs), never business content.
3. **Fail-closed verification** — TLC must explicitly say "no error"; ambiguity =
   failure. Unverified specs cannot ship.
4. **Fail-honest runtime** — after `CORRECTION_CAP` (3) unrecovered out-of-order tries at
   one state, the agent fails rather than faking progress or looping.
5. **Harness-agnostic core** — `monitoring`, `sdk_adapter`, and `opencode_adapter` reuse
   `CoordinationContext` / `ProtocolMonitor` / `StateTracker` **unchanged**; `mixed_run`
   proves it.
6. **Observability never gates** — the event bus / live view can fail or be disabled with
   zero effect on correctness.
7. **Naming is authoritative** — `benchmark/.../metadata.json` IDs must match `ir.json`
   exactly.

---

## 10. Appendix C — Directory map

```
tracefix/
├── pipeline/                 # ① DESIGN & VERIFY
│   ├── cli.py loop.py tool_client.py tools.py prompts.py   # outer agentic loop
│   └── pipeline/             # inner deterministic compiler
│       ├── validator.py schema.json
│       ├── pluscal_generator.py pluscal_compiler.py tlc_runner.py
│       ├── trace_parser.py error_formatter.py
│       └── pluscal_parser.py            # tree-sitter → states.json
├── cli/                      # tla-verify-pluscal (no-LLM CLI over the inner pipeline)
└── runtime/                  # ② EXECUTE
    ├── store.py              # LockStore · CounterStore · MessageStore · ConversationStore
    ├── workspace_layout.py   # spec/ prompts/ output/ resolution
    ├── monitoring/           # OpenAI-loop harness + the shared CORE
    │   ├── coord.py monitor.py state_tracker.py correction.py   # ← reused by all harnesses
    │   ├── agent_runner.py orchestrator.py cost.py result_saver.py
    │   └── event_bus.py live_server.py live_view.py visualize.py  # observability
    ├── sdk_adapter/          # Claude Agent SDK harness (dispatch · mcp_server · sdk_runner)
    ├── opencode_adapter/     # opencode harness (config_gen · driver · orchestrator)
    ├── coord_mcp/            # shared stdio MCP server (coordination tools)
    ├── domain_mcp/           # typed domain tools — impl: local Python impls over MCP
    ├── coordination/         # distributed seam (backend · service · client)
    └── mixed_run.py          # cross-harness proof

benchmark/                    # fully-specified tier (48 tasks = 16 scenarios × E/M/H)
├── loader.py
├── descriptions/{id}/        # description.md · tools.json · metadata.json
├── environments/{id}/        # sim.py · tools_impl.py · checklist.json
├── underspecified/{id}/      # narrative tier — description.md · meta.json (prose, no scaffolding)
├── underspec_eval.py         # property-based scorer for the narrative tier
└── tools/                    # ToolRegistry · SimContext base
```

---

*Generated for the TraceFix open-source release. For build/run commands see the root
[`README.md`](../README.md) and [`CLAUDE.md`](../CLAUDE.md). The first-choice way to design
a protocol interactively is the **TraceFix TUI** (`tracefix-tui`); for users on their own
agent harness the human-in-the-loop workflow lives in the `/tla-verify-pluscal` and
`/tla-prompt-gen` skills (the single source the TUI also consumes via `tla-verify-pluscal
guide`).*
