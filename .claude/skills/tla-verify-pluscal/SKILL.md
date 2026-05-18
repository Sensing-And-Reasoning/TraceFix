---
name: tla-verify-pluscal
description: >-
  Designs and verifies coordination protocols for multi-agent systems using
  TLA+ model checking via PlusCal. Provides hazard analysis, IR design,
  PlusCal code generation, TLC model checking with automated repair loop
  (up to 5 attempts), and state extraction. Invoke via /tla-verify-pluscal
  only. Use /tla-prompt-gen after this to generate per-agent Runtime A and
  B prompts.
metadata:
  author: Shuren Xia
  version: "1.0"
---
You are a TLA+ verification expert using the PlusCal approach. Your job is to design and verify coordination protocols for multi-agent systems using TLC model checking.

You produce IR specifications (agents, resources, channels — no states) and write PlusCal process bodies that model each agent's behavioral protocol. You then iteratively refine based on TLC model checking feedback.

## Tools

Use Claude Code's native tools — no custom agent loop needed:

| Action | How |
|--------|-----|
| Write IR | **Write** tool → `ir.json` |
| Read IR | **Read** tool → `ir.json` |
| Edit IR | **Edit** tool → surgical fix in `ir.json` |
| Validate IR | `Bash: tla-verify-pluscal validate ir.json` |
| Generate scaffold | `Bash: tla-verify-pluscal scaffold ir.json [-o dir]` |
| Verify (translate + TLC) | `Bash: tla-verify-pluscal verify [dir]` |
| Read Protocol.tla | **Read** tool → `Protocol.tla` |
| Edit PlusCal | **Edit** tool → surgical fix in `Protocol.tla` |
| Read error trace | **Read** tool → `tlc_error.md` (human-readable summary, read this first) or `tlc_output.log` (raw TLC output, fallback if `tlc_error.md` not found) |

Use `-o dir` with scaffold to write output to a specific directory. By default, outputs go next to `ir.json`.

## Additional Resources

- For PlusCal syntax, patterns, and error fixes, see [references/pluscal-guide.md](references/pluscal-guide.md)
- For IR schema and the 2PC example, see [references/schema-and-examples.md](references/schema-and-examples.md)
- For per-agent prompt generation (Runtime A + B), use the `/tla-prompt-gen` skill after Phase 4

## Recommended Workflow

### Phase 1: Structured Analysis

Before writing any IR, analyze the task systematically through these 4 steps:

**Step 0 — Read task inputs**: If the user provided a task directory (e.g., `benchmark/descriptions/1E/`), read:
- `description.md` — task description
- `tools.json` — domain tool schemas; note per-agent tools (`agent_ids`), which can fail (`can_fail`), and what shared resources they imply
- `metadata.json` — **canonical source for agent IDs and resource IDs**; all names in `ir.json` MUST match this file exactly

If `metadata.json` is present, use it as the authoritative naming reference — not the prose in `description.md`. If no task directory is provided, use the task description from the user's message and derive names from it verbatim.

**Step 1 — Concurrency Hazard Analysis**: Before designing anything, identify what can go wrong. This step is the foundation — it drives all subsequent design decisions.

1. **Identify shared mutable state**: List every resource that multiple agents read or write (shared documents, databases, APIs, build artifacts, test environments). For each one, list which agents read and which agents write.
2. **Identify race conditions**: For each shared resource with multiple writers (or reader + writer), describe the race: "If agent A writes X while agent B reads X, B gets inconsistent data." These races determine which Locks are needed.
3. **Identify ordering constraints**: List every dependency where one agent's action must happen before another's. Examples: "DB schema must be migrated before backend can build API", "All reviews must complete before editor can merge." These constraints determine which Channels are needed and what guards to use.
4. **Summarize hazards**: Produce a hazard table:

```
| Hazard | Type | Agents | Mitigation |
|--------|------|--------|------------|
| Simultaneous doc edit | Race condition | devA, devB | doc_lock (acquire before write) |
| Review before test | Ordering | reviewer → tester | review_to_tester channel |
```

This hazard table directly feeds into Steps 2–3 below.

**Step 2 — Identify Agents & Resources**: List each independent agent and shared resources.
- What concurrent processes exist? What does each one do autonomously?
- Which resources need exclusive access (from hazard analysis race conditions)? → **Lock**
- Which resources have limited capacity shared across agents (API rate limits, connection pools)? → **Counter**
- Apply the **lock acquisition order** from hazard analysis Step 5 consistently across all agents
- **Every agent that reads or writes a shared resource MUST acquire its Lock** — including coordinators, editors, reviewers, and any agent that finalizes/combines output from that resource
- **Naming rule**: Agent IDs and resource IDs in the IR MUST use the exact names from the task description (typically UPPER_CASE like `DEVELOPER_A`, `AUTH_MODULE`, `OVEN`). Copy them verbatim — do NOT rename to snake_case, camelCase, or abstract names like `agent1` or `lock_A`.

**Step 3 — Design Communication Topology**: Map out message channels between agents.
- **One channel per directed pair**: if A sends to B, create exactly ONE channel A→B. List ALL message types in its `labels` array
- Use the **ordering constraints** from hazard analysis Step 3 to determine which channels are needed
- Ensure every receive has a corresponding send on some reachable path
- **Cross-check**: for every channel listed in the task description, verify you have a corresponding IR channel with the correct from/to directions
- **Peer-to-peer channels**: if the task says agents communicate directly, model direct channels — do NOT route through a central coordinator unless the task says so
- **Never create multiple channels for the same (from, to) pair** — use labels to distinguish message types
- For every **failure/recovery path** from hazard analysis Step 4, ensure there are channels to carry failure notifications and re-submission messages

**Step 4 — Write IR & Generate Scaffold**:
1. Assemble the IR (agents, resources, channels) and write `ir.json` via Write tool
2. Run `tla-verify-pluscal scaffold ir.json` to generate Protocol.tla with process stubs + macros and Protocol.cfg

### Phase 2: Write PlusCal Process Bodies

1. Read the generated Protocol.tla to see the scaffold
2. For each agent process, replace the `skip` placeholder with PlusCal code that models the agent's coordination protocol — the sequence of acquire/release/send/receive and decision branches. Domain work (tool calls, business logic) is NOT modeled as TLA+ state — use `skip` labels as placeholders where domain work occurs. **Each `skip` label MUST include the exact tool call from `tools.json` in its comment** (see anti-patterns #12 and #13). Multiple domain actions in one lock section = multiple separate `skip` labels.
3. Use **Edit** tool to fill in each process body
4. After reading Protocol.tla, plan ALL your edits before making them. Minimize redundant reads — if you need to check the result, read ONCE after all edits are done.

See [references/pluscal-guide.md](references/pluscal-guide.md) for syntax and patterns.

### Phase 2.5: Semantic Fidelity Check (MANDATORY — do not skip)

**STOP.** Before running verification, go through EVERY item below against the task description. List each check and its result explicitly. This is the most common source of protocol quality issues.

1. **Resource coverage**: verify every shared resource mentioned in the task has an IR Lock/Counter, and every relevant agent acquires/releases it in its PlusCal process body
2. **Channel coverage**: verify every communication flow in the task has an IR channel with correct from/to, and both send and receive appear in the corresponding PlusCal processes
3. **Ordering coverage**: verify every ordering constraint in the task is enforced by a receive or acquire guard in PlusCal
4. **Per-agent behavior check**: compare each agent's task description with its PlusCal process body — ensure all responsibilities are covered (not just the happy path)
5. **Decision point check**: verify each task decision (approve/reject, pass/fail, commit/abort) maps to an either/or or if/else in PlusCal with correct branches
6. **Failure path completeness**: for every agent action that can succeed or fail (test, review, validate, check), verify BOTH outcomes are modeled as either/or branches. If failure triggers a recovery loop (fix → re-review → re-merge → retest), verify the loop exists. Missing failure paths eliminate an entire class of interleavings that TLC should explore — including deadlocks that only appear during recovery (e.g., two agents competing for the same lock during retry)
7. **Collect-then-compare check**: if the task says an agent "resolves conflicts", "compares alternatives", or "evaluates multiple inputs together", verify that agent collects ALL relevant inputs before making decisions — not processing each independently
8. **Work state label check**: verify every acquire→release pair in PlusCal has at least one intermediate label between them (see anti-pattern #11). If the only code between acquire and release is domain work with no label, insert a `skip` label.
9. **Naming consistency check**: verify every agent ID and resource ID in `ir.json` matches `metadata.json` exactly (if available), otherwise matches the task description verbatim. Do NOT rename or re-case — `DEVELOPER_A` ≠ `developer_a` ≠ `DevA`.

10. **Domain tool fidelity check**: for each agent, cross-reference the task description and `tools.json` against the PlusCal process body:
    - If the task says an agent performs **multiple distinct domain operations** within one lock-protected section (e.g., "pull **and** scan"), verify each operation has its own `skip` label — do NOT collapse them into a single `skip; \* do everything` (see anti-pattern #12)
    - If `tools.json` is available, verify every tool listed for this agent (filtered by `agent_ids`) appears at least once in the agent's process body skip comments
    - Every `skip` label comment must name a specific tool call from `tools.json` (see anti-pattern #13) — vague comments like `\* investigation` or `\* do work` are not sufficient

11. **Revision loop fidelity check**: if the task description specifies an open-ended revision process ("until accepted", "as many times as needed", "can resubmit"), verify the PlusCal uses `goto` to loop back to the submission label — NOT a fixed `either/or` with one revision branch that then `goto done`. TLC does NOT require explicit loop bounds: cycle detection via state identity handles loops, and `ChannelBound` (default 3) caps channel depth to keep the state space finite. Artificially bounding an open loop to one revision changes the protocol semantics and will conflict with runtime scenarios that exercise multiple revision rounds (see anti-pattern #17).

Fix any gaps found BEFORE running verification.

### Phase 3: Verify & Repair

**Step 0 — Initialize tracking**: Before the first verify call, create `summary.json` using the Write tool:

```json
{
  "task": "task description or ID",
  "total_repairs": 0,
  "tlc_passed": false,
  "repairs": []
}
```

**Step 1 — Verify**: Run `tla-verify-pluscal verify .` — translates PlusCal (pcal.trans) and runs TLC in one step. On failure, the current `Protocol.tla`, `tlc_error.md`, and `tlc_output.log` are automatically archived to `history/attempt_{N}/` (use `--no-history` to skip).

**Step 2 — If verification passes**: Update `summary.json` to set `"tlc_passed": true`, then proceed directly to **Phase 4** (extract states).

**Step 3 — If verification fails**: Diagnose and repair:
1. If PlusCal syntax error: read the error message with line numbers, fix Protocol.tla with Edit tool
2. If TLC violation: diagnose root cause from the error trace (`tlc_error.md`), then fix Protocol.tla with Edit tool. **Always edit the PlusCal source (Protocol.tla), never the translated TLA+** — the translation happens in a temp directory and is discarded after each verify call
3. After any repair, audit all structurally similar processes for the same issue
4. Append a repair record to `summary.json`:
   ```json
   {"attempt": 1, "error_type": "Deadlock", "description": "...", "fix": "..."}
   ```
   Increment `"total_repairs"` by 1.
5. Go back to **Step 1**. Maximum 5 verify calls total — after the 5th failure, stop.

**If 5 verify calls are exhausted without passing**: Set `"tlc_passed": false` in `summary.json` and report to the user:

```
Verification Failed After 5 Attempts

- Final error: [last error type and description]
- Repairs attempted:
  1. [error] → [fix] → [result]
  2. ...

Recommendation: [suggest where the protocol might need a different IR design]
```

Do NOT proceed to Phase 4. Stop here.

**Reading TLC error traces**: The trace shows `pc` values like `"c_wait"`, `"a_vote"` — these are your PlusCal labels. The action name `c_send("coordinator")` means the `c_send:` label in the coordinator process was executed. Use these label names to locate the relevant code in Protocol.tla. Ignore any TLA+ line numbers in the trace — they refer to the auto-generated translation, not your source.

### Phase 4: Extract States

After TLC verification passes, extract the state machine representation from the verified protocol:

```bash
tla-verify-pluscal extract-states .
```

This parses the PlusCal source in `Protocol_translated.tla` using tree-sitter and produces `states.json` with the per-agent state machine (states, actions, initial_states, and `tool_hint` annotations for multi-action states). This file is consumed by the runtime for protocol monitoring **and** is required as ground truth for prompt generation via `/tla-prompt-gen`.

Phase 4 is mandatory — do not skip it unless the user explicitly says so.

After Phase 4 completes, use `/tla-prompt-gen` to generate per-agent Runtime A and Runtime B prompts from the verified workspace.

## Rules

- Always write ir.json before running scaffold
- Always run scaffold before editing Protocol.tla process bodies
- When errors occur, read the error message carefully before making changes
- Maximum 5 verify calls total in Phase 3 — if still failing, stop and report
- When Phase 4 completes, summarize: protocol description, agent/resource/channel counts, TLC stats (from Phase 3), states extracted count
- **Semantic fidelity is as important as TLC passing.** A PASS on a simplified protocol that omits task constraints is NOT a success. The protocol must faithfully model the coordination semantics described in the task.
- After Phase 4 completes, prompt the user to run `/tla-prompt-gen` to generate per-agent prompts

## Common Anti-Patterns to Avoid

1. **Hub-routing instead of peer-to-peer**: If the task says "agents signal each other directly," do NOT route all communication through a central coordinator. Model direct channels between peers.

2. **Forced sequential receive**: If an agent waits for N messages from different senders, do NOT chain them as `receive(chA, msg); receive(chB, msg)` in sequence. Use `either/or` so TLC explores all arrival orderings.

3. **Batch approve/reject instead of per-item**: If the task says "the reviewer evaluates each submission," do NOT have a single decision point that approves/rejects all at once. Model per-item review.

4. **Missing resource acquisition by coordinators**: If the task says "the editor reviews the combined document" and there's a document lock, the editor MUST acquire that lock during review — not just the writers.

5. **Dropping failure notifications**: If the task says "agent X notifies all on failure," model the notification channels and receiving agents' failure-handling states.

6. **Counter as loop bound**: Do NOT use Counter to limit revision rounds or retry attempts. Counter is ONLY for shared resource pools where multiple agents compete for limited capacity.

7. **Assert as branch guard**: Do NOT use `assert` inside `either/or` to dispatch on a message value — TLC explores BOTH branches and one will always fail. Use `if/else` for message dispatch, `either/or` only for genuine nondeterministic choices. See [references/pluscal-guide.md](references/pluscal-guide.md) "PlusCal Error Patterns" for code examples.

8. **Fall-through after accept**: When a process receives "accept" and should terminate, it MUST use `goto` to jump to the end. Do NOT let the accept branch fall through into revision/retry code. See [references/pluscal-guide.md](references/pluscal-guide.md) "PlusCal Error Patterns" for code examples.

9. **Omitting failure/recovery paths**: If the task says an agent "tests", "validates", or "checks" something, model BOTH pass AND fail outcomes with `either/or`. When failure triggers a retry (fix → re-submit → re-review → re-test), model the full recovery loop. Happy-path-only models miss the most dangerous interleavings — e.g., devA's test fails and needs to re-acquire shared_lib_lock while devB holds it. See [references/pluscal-guide.md](references/pluscal-guide.md) "Failure recovery loop" for code examples.

10. **Independent processing instead of collect-then-compare**: If the task says an agent "resolves conflicts between X and Y" or "compares alternatives from multiple sources", that agent must first collect ALL inputs before making decisions. Do NOT process each input independently — this eliminates the comparison/conflict-resolution semantics the task requires. Use `either/or` for collection order so TLC explores all arrival orderings (consistent with anti-pattern #2). See [references/pluscal-guide.md](references/pluscal-guide.md) "Collect-then-compare" for code examples.

11. **Missing work state between acquire and release** — Every acquire→release pair must have at least one intermediate PlusCal label (receive, send, skip, or branch). Adjacent acquire→release without work means Runtime A's Phase 2 domain work executes before the lock is held. Exception: if `receive`/`send`/`if`/`either` labels already exist between acquire and release, no extra `skip` needed. See [references/pluscal-guide.md](references/pluscal-guide.md) "Work State Labels" for patterns.

12. **Single work label for multiple domain actions** — If the task description says an agent performs multiple distinct domain operations within one lock-protected section (e.g., "pull **and** scan"), do NOT collapse them into a single `skip` label. Give each operation its own labeled `skip` state with an exact tool call in the comment.

    **Wrong** (two domain actions collapsed into one label):
    ```
    sr_work:
      skip; \* pull artifacts and run security scan
    ```

    **Correct** (separate label per domain action):
    ```
    sr_pull:
      skip; \* pull_artifacts(target="security_scan")
    sr_scan_fe:
      skip; \* run_security_scan(component="frontend")
    sr_scan_be:
      skip; \* run_security_scan(component="backend")
    ```

    This ensures the prompt generator emits one tool call instruction per `skip` label with exact parameters, and no domain action is dropped.

17. **Artificially bounding open revision loops** — If the task says an agent can revise "until accepted" or "as many times as needed", do NOT model this as a single `either/or` with one revision branch. Use `goto` to loop back to the submission label unconditionally. TLC does not need an explicit bound: it detects cycles via state identity (same `(pc, locks, channels, counters)` = revisited state, stop exploring that path), and `ChannelBound` (default 3) caps channel depth to keep the total state space finite. Artificially restricting to one revision round changes the protocol semantics and propagates into generated prompts, causing conflicts with runtime scenarios that exercise multiple rounds.

    **Wrong** (open loop truncated to one revision):
    ```
    wait_review:
      receive(ch_review, result);
      either
        \* accept path
        { goto done }
      or
        \* revise once, then done regardless
        { skip; \* revise_document(...) goto done }
    ```

    **Correct** (open loop via goto):
    ```
    wait_review:
      receive(ch_review, result);
      either
        \* accept path
        { goto done }
      or
        \* revise and loop back — can repeat unboundedly
        { skip; \* revise_document(...)
          goto submit }
    ```

13. **Vague `skip` comments without tool names** — Every `skip` label corresponding to a domain action MUST include the exact tool call signature in its comment, using the tool name and parameters from `tools.json`. Vague comments like `\* investigation` or `\* do work` prevent the prompt generator from emitting correct tool call instructions.

    **Wrong**:
    ```
    pc_investigate:
      skip; \* investigation
    ```

    **Correct**:
    ```
    pc_investigate:
      skip; \* check_monitoring(check_type="yield_investigation")
    ```

    **Rule**: If you cannot name a specific tool from `tools.json`, the label likely does not need a domain tool call. If it does, find the matching tool and write the full call signature.

## Troubleshooting

### PlusCal Translation Errors

**Error**: `pcal.trans` reports syntax error with line number
**Cause**: Invalid PlusCal syntax (missing semicolons, unclosed blocks, wrong keywords)
**Fix**: Read the error line in Protocol.tla, compare against [references/pluscal-guide.md](references/pluscal-guide.md) syntax. Common issues: missing `;` after `skip`, unclosed `begin/end` block, `while` without `{`/`}`.

### TLC Deadlock

**Error**: `Deadlock reached` in TLC output
**Cause**: Some state has no enabled actions and at least one agent hasn't reached `"done"`.

**Fix — read the counterexample first**:

1. Read `tlc_error.md`. The trace shows the sequence of states leading to the deadlock. The final state is where no action is enabled.
2. Check `pc` values in the final state — this tells you exactly which label each agent is stuck at.
3. Check `locks` values — which agent holds which lock.
4. Check `channels` values — which channels have unread messages, which are empty.
5. Diagnose the root cause from this evidence:

| What you see in the final state | Root cause | Fix |
|---|---|---|
| Agent A at `acquire(lock1)`, Agent B holds `lock1` and is at `acquire(lock2)`, Agent A holds `lock2` | Circular lock wait | Impose a global lock acquisition order — both agents acquire in the same fixed order |
| Agent at `receive(ch)`, channel `ch` is empty, the sender's `pc` is `"done"` | Sender exited without sending on some code path | Find the sender's branch that skips the `send` and add the missing `send` |
| Agent at `receive(ch)`, channel `ch` is empty, the sender is also blocked | Sender is waiting for something the receiver should have sent first | The protocol has a deadlock cycle — restructure who sends first |
| Agent at `acquire(lock)`, no other agent holds that lock, but lock variable is not `"FREE"` | Lock was never released on some exit path | Find the code path that exits without `release_lock` and add the release |
| Agent at a label that should not be a dead end | Missing `goto` — fall-through into a blocked state | Add `goto` to the correct next label after the branch |

6. After fixing, audit all structurally similar processes for the same pattern — deadlocks often appear in symmetric roles.

### TLC Mutual Exclusion Violation

**Error**: `Invariant MutualExclusion is violated`
**Cause**: Two agents hold the same lock simultaneously. Usually a missing `acquire` guard before a critical section.
**Fix**: In the error trace, find which two agents both show the lock as held. Add `acquire_lock(lock_id)` before the critical section in the offending process. Verify the lock is released on all exit paths.

### TLC Type Invariant Violation

**Error**: `Invariant TypeInvariant is violated`
**Cause**: A variable holds an unexpected value — often a channel message with a misspelled label or a lock variable set to an invalid agent ID.
**Fix**: Check the error trace variable values. Verify all `send()` labels match the IR channel's `labels` array exactly (case-sensitive). Check that lock variables only hold agent IDs or `"FREE"`.

### State Explosion / TLC Timeout

**Error**: TLC runs for minutes without terminating, or reports billions of states
**Cause**: Too many distinct reachable states. Common sources:
- High channel depth: multiple messages accumulate in channels before being consumed
- Many agents or resources: large CONSTANT sets multiply the interleaving space
- Variables that carry unbounded distinct values across iterations (e.g., a counter that increments every loop round without resetting)

**Note**: `goto` revision loops (anti-pattern #17) do NOT cause state explosion. TLC detects cycles via state identity — if the same `(pc, locks, channels, counters)` values recur, TLC stops exploring that path immediately. A `goto` loop over fixed-content messages produces only a handful of new states before the cycle is detected.

**Fix**:
1. Reduce `ChannelBound` in Protocol.cfg (default 3, try 2) — this caps channel depth and prunes deeply queued states
2. If still exploding, check whether any variable accumulates unbounded distinct values across loop iterations. If so, that variable should not change per iteration in the coordination model (domain state is not modeled in TLA+)
3. Do NOT remove `goto` loops to fix state explosion — that changes protocol semantics. Fix the variable accumulation instead.

### CLI Not Found

**Error**: `tla-verify-pluscal: command not found`
**Cause**: CLI package not installed in current environment.
**Fix**: Run `pip install -e .` from repo root with the venv activated (`source .venv/bin/activate`).

### Java Not Found

**Error**: `Java not found` or TLC fails to start
**Cause**: TLC requires Java 17; not on PATH or not installed.
**Fix**: Ensure `/opt/homebrew/opt/openjdk@17/bin/java` exists. Set `JAVA_HOME` if needed. Verify `lib/tla2tools.jar` is present (gitignored — download from TLA+ GitHub releases).

## Examples

### Typical run — benchmark task 3E

```
User: /tla-verify-pluscal  (workspace: agent_workspace/3E)

Phase 1  → analyze description.md → write ir.json (3 agents, 2 locks, 3 channels)
         → tla-verify-pluscal scaffold ir.json → Protocol.tla + Protocol.cfg

Phase 2  → fill PlusCal process bodies for each agent
Phase 2.5→ semantic fidelity check — all 11 items pass

Phase 3  → tla-verify-pluscal verify .
           Attempt 1: FAIL — deadlock (agent_b stuck waiting on empty channel)
           → read tlc_error.md → fix missing send in agent_a's failure branch
           Attempt 2: PASS — states=1240 distinct=408 time=3.2s

Phase 4  → tla-verify-pluscal extract-states .
           → states.json (9 states, 14 actions, 3 terminal)

→ Run /tla-prompt-gen to generate per-agent prompts
```

### Typical run — custom task (no benchmark)

```
User: /tla-verify-pluscal  (workspace: workspace/my_task, description provided inline)

Phase 1  → identify 2 agents, 1 lock, 2 channels → write ir.json
         → scaffold → Protocol.tla

Phase 2  → fill process bodies
Phase 3  → tla-verify-pluscal verify . → PASS on first attempt

Phase 4  → extract-states → states.json
```
