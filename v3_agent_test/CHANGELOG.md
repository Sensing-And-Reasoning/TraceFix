# v3_agent Changelog

`v3_agent` is a fork of `v3_agent` with TLC state space optimizations and IR design improvements. Created to address Hard benchmark tasks (3H, 4H) that timed out due to state space explosion in the original `v3_agent`.

## Changes from v3_agent

### 1. Channel Depth CONSTRAINT (skeleton_generator.py)

**Problem**: Unbounded channels cause infinite state space. 29 channels × 7 agents → TLC timeout.

**Solution**: Added `channel_bound` parameter (default 3) to `generate_tla()` and `generate_tlc_config()`.
- TLA+ spec emits `ChannelBound == \A ch \in DOMAIN channels: Len(channels[ch]) <= 3`
- TLC config references it as `CONSTRAINT ChannelBound`
- Bounds per-channel states from unbounded to at most `channel_bound` messages

### 2. Agent-Specific Next Formula (skeleton_generator.py)

**Problem**: `\E agent \in Agents: Action(agent)` evaluates every action's guard for every agent. For 7 agents × 107 actions = 749 evaluations per state.

**Solution**: Emit per-agent disjunctions in `Next`:
```tla
Next ==
  Action1("coordinator") \/ Action2("coordinator") \/ ...
  \/ Action3("workerA") \/ ...
```
Tracks `(action_name, agent_id)` pairs during generation. Each action is evaluated only for its owning agent — 107 evaluations per state instead of 749.

### 3. String Messages Instead of Records (skeleton_generator.py)

**Problem**: TLA+ records `[label |-> "prepare"]` consume more memory per state than simple strings.

**Solution**: `_build_msg_record()` returns `"prepare"` instead of `[label |-> "prepare"]`. Receive guards use `Head(channels[ch]) = "prepare"` instead of `Head(channels[ch]).label = "prepare"`.

### 4. Multi-Core TLC + Heap (tlc_runner.py)

- Changed `-workers "1"` → `-workers "auto"` (uses all CPU cores)
- Added `-Xmx4g` JVM flag for large state spaces

### 5. Safety-Only Verification (skeleton_generator.py, tlc_runner.py, tools.py)

**Problem**: Liveness checking (EventuallyTerminated) requires expensive SCC analysis and is unrealistic for LLM MAS with nondeterministic loops (e.g., reviewer can always reject → infinite loop is valid business logic, not a coordination bug).

**Solution**: Dropped liveness checking entirely. Deadlock remains a safety property detected natively by TLC.

- **skeleton_generator.py**:
  - `Terminated` defined before `Next` (TLA+ requires definitions before use)
  - Added `(Terminated /\ UNCHANGED vars)` stuttering to `Next` — terminal states are not false deadlocks
  - `Spec == Init /\ [][Next]_vars` — no fairness (`WF_vars(Next)` removed)
  - Removed `EventuallyTerminated` operator
- **tlc_runner.py**: Removed `-deadlock` flag — TLC natively detects deadlock (no enabled action in non-terminal state)
- **tools.py**: `verify_ir()` simplified from two-phase (safety then liveness) to single-phase safety-only
- **prompts.py**: Liveness violation section replaced with note explaining safety-only verification

**Deadlock detection verified**: Circular lock wait (A holds lock1 wants lock2, B holds lock2 wants lock1) correctly reported as deadlock. Terminal states (all agents done) do NOT trigger false deadlock.

### 6. One Channel Per Directed Pair + Labels (schema.json, validator.py, prompts.py)

**Problem**: LLMs create many fine-grained channels between the same agent pair (e.g., `prepare_ch`, `commit_ch`, `abort_ch` all from coordinator to workerA). This explodes TLC state space and doesn't match the real communication model — agents have one link between them.

**Solution**: Enforce one channel per (from, to) pair. Different message types distinguished by `labels`.

- **schema.json**: Added `labels` as required field on channels (array of strings, minItems 1)
  ```json
  {"id": "coord_to_A", "from": "coordinator", "to": "workerA", "labels": ["prepare", "commit", "abort"]}
  ```
- **validator.py**: Three new semantic checks:
  - Duplicate (from, to) pair → error with suggestion to use labels
  - Send label not in channel's declared labels → error
  - Missing label on send/receive when channel declares labels → error
- **prompts.py**: Updated channel documentation, Step 3 workflow, and 2PC example with labels

### 7. Counter Semantics Clarification (prompts.py)

**Problem**: Counter was used for loop bounds (e.g., `retry_budget` with initial=2). This is wrong — loops should be unbounded state machine cycles.

**Solution**: Counter = shared resource pool (counting semaphore) for API rate limits, connection pools, GPU slots. NOT for loop iteration bounds.

- Removed Budget Counter guidance from prompts
- Updated 2PC example: removed `retry_budget` Counter, abort is terminal outcome (not retry)
- Loops are unbounded cycles bounded at TLC level by Channel CONSTRAINT

### 8. Tree-Sitter PlusCal Parser (pluscal_parser.py)

**Problem**: `tla_parser.py` (~1321 lines of regex) parses the **translated TLA+** output, which loses structural information from the original PlusCal source. It cannot distinguish:
- **Message dispatch**: `if (msg = "approve")` — checking a just-received message
- **Local variable routing**: `if (revA = "approve")` — checking a previously stored variable

Both compile to identical TLA+ syntax, so the regex parser guesses (often wrong for Hard tasks like 3H).

**Solution**: New `pluscal_parser.py` (~1050 lines) uses `tree-sitter-tlaplus` to parse the PlusCal source directly from the `(* --algorithm ... *)` block comment. PlusCal preserves:
- `receive(ch, var)` — which variable receives the message
- Label scope boundaries — fall-through targets are unambiguous
- Macro names — `send`/`receive`/`acquire_lock`/`release_lock` identified directly, no regex reverse-engineering

**Architecture**:
```
Protocol_translated.tla (contains PlusCal source)
  → tree-sitter parse → CST
  → extract pcal_algorithm → pcal_process list
  → _walk_body_stmts() recursive traversal → LabelBlock list (with fall_through)
  → _block_to_actions() conversion → ParsedAction
  → _merge_receive_dispatch + _infer_else_labels (reused from tla_parser)
  → ParseResult (identical format to tla_parser output)
```

**PlusCal patterns handled** (8 base + 2 nested):
| Pattern | Example | Description |
|---------|---------|-------------|
| P1 Sequential labels | 9E | Linear state chain |
| P2 receive + if dispatch | 10E | Message label branching |
| P3 receive + local var routing | 3H | Different recv var vs condition var → no merge |
| P4 while loop | 4M | Guard true/false + body loops back |
| P5 either/or with labels | 4M | Nondeterministic receive from multiple channels |
| P6 if with labels | 3H | Conditional with labeled branches |
| P7 Multi-statement label | 3H | Multiple effects in one atomic step |
| P8 either/or without labels | 4M | Nondeterministic send |
| Chained else-if + labels | 7H | `if/else if/else` each with internal labels |
| Deeply nested labels | 8E | Labels inside either-or inside if-else |

**CLI integration** (`tla_verify_pluscal/cli.py`):
- `tla-verify-pluscal extract-states <dir>` — now uses PlusCal parser by default
- `tla-verify-pluscal extract-states --legacy <dir>` — falls back to regex TLA+ parser

**Cross-validation**: All 27 available IRs produce semantically identical output between old and new parser (17 exact match + 10 ordering-only diffs in release/send array order).

**Tests**: `test_pluscal_parser.py` — 365 tests (unit + integration + cross-validation + batch structural checks).

| File | Description |
|------|-------------|
| `pipeline/pluscal_parser.py` | Tree-sitter PlusCal parser (new) |
| `tests/test_pluscal_parser.py` | 365 tests for PlusCal parser (new) |
| `pipeline/tla_parser.py` | Regex TLA+ parser (unchanged, kept as fallback) |
| `tla_verify_pluscal/cli.py` | `extract-states` default → PlusCal parser, `--legacy` → TLA+ parser |

## Test Results

| Task | v3_agent (before) | v3_agent (after) | Notes |
|------|-------------------|----------------------|-------|
| 3E   | PASS              | PASS (11 tools, 0 repairs, 4 channels) | Channels comply with one-per-pair + labels |
| 3H   | FAIL (timeout)    | TLC completes in ~1s (113K-1.1M states) | Agent loop may still fail on repair |
| 4H   | FAIL (timeout)    | TLC completes in ~1s (113K states) | Deadlock detected, agent enters repair |

## File Summary

| File | Changes |
|------|---------|
| `pipeline/schema.json` | `labels` required on channels |
| `pipeline/validator.py` | Duplicate (from,to) check, label consistency checks |
| `pipeline/skeleton_generator.py` | ChannelBound CONSTRAINT, agent-specific Next, string messages, Terminated before Next, safety-only Spec |
| `pipeline/tlc_runner.py` | `-workers auto`, `-Xmx4g`, removed `-deadlock` flag |
| `tools.py` | Single-phase `verify_ir()` (removed two-phase liveness logic) |
| `prompts.py` | Channel labels, one-per-pair rule, Counter semantics, safety-only note, updated 2PC example |
