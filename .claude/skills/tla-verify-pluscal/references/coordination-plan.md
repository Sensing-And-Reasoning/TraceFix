# Coordination Plan (`plan.md`) — format & PlusCal mapping

The coordination plan is the **review artifact** produced in Phase 1.5, between the IR/scaffold
and the PlusCal. It is a per-agent, human-readable step outline — readable without TLA+ — so a
reviewer can catch semantic errors (wrong topology, missing failure path, wrong order) *before*
the expensive PlusCal + TLC round. It is NOT verified itself; the verified source of truth stays
the PlusCal. Think of it as the agreed contract that the PlusCal then encodes faithfully.

## Format

One block per agent. Header line states what the agent shares and its channels; then numbered
steps, each tagged with a type.

```
Agent: <ID>   shares: <resource>(lock|counter)   listens: <ch>(<labels>)   notifies: <ch>(<labels>)
  1. [receive] <label> ← <SENDER>
  2. [lock] acquire <resource>
  3. [domain: <tool_name>(<args>)]            # real work; add ", can_fail" if it can fail
  4. [send <label>] → <RECEIVER>
  5. [branch on <label>] ├─ <a> → N  └─ <b> → M
  6. [retry loop → step K]                    # recovery loop back to step K
  7. [unlock] release <resource>
  8. [done]
```

Compose tags on one line when they happen in one atomic step, e.g.
`5. [unlock] release PROD_DB ; [send migrated] → ONCALL`.

## Worked example (the `hotfix` DBA agent)

```
Agent: DBA   shares: PROD_DB(lock)   listens: oncall_to_dba(migrate)   notifies: dba_to_oncall(migrated)
  1. [receive] migrate ← ONCALL
  2. [lock] acquire PROD_DB
  3. [domain: apply_migration()]
  4. [domain: verify_schema(), can_fail]
       ├─ clean  → 5
       └─ failed → [domain: rollback_migration()] → [retry loop → 4]
  5. [unlock] release PROD_DB ; [send migrated] → ONCALL
  6. [done]
```

## Step type → PlusCal construct

| Plan tag | PlusCal | Notes |
|---|---|---|
| `[receive] x ← S` | `receive(ch, msg)` | `ch` is the S→this channel |
| `[send x] → R` | `send(ch, "x")` | `ch` is the this→R channel; `x` must be in its `labels` |
| `[lock] acquire R` | `acquire_lock(R)` | one label; a work state must follow before release |
| `[unlock] release R` | `release_lock(R)` | every acquired lock released on every exit path |
| `[domain: t()]` | labeled `skip; \* t()` | NOT modeled as TLA+ state — just a comment; one label per distinct action |
| `[domain: t(), can_fail]` | `either { ok } or { recovery }` | the `can_fail` flag is why this becomes a branch (see anti-pattern #9) |
| `[branch on x]` | `if (msg = "x") {...} else {...}` | message dispatch uses `if/else`, never `assert` |
| `[retry loop → K]` | `goto <label K>` | unbounded loop; TLC cycle-detects (see anti-pattern #17) |
| `[done]` | the process's `*_done:` terminal label | every process ends by reaching its `*_done:` label |

## Review checklist (what the plan is FOR)

Confirm against the task description, before writing PlusCal:
- every shared resource has a `[lock]`/`[unlock]` pair on every agent that touches it;
- every communication flow appears as a `[send]` on one side and a `[receive]` on the other;
- every ordering constraint is enforced by a `[receive]`/`[lock]` that gates the dependent step;
- every `can_fail` domain action has a recovery branch (and a `[retry loop]` if it re-coordinates);
- every agent ends at `[done]`.

Fix the plan (cheap) rather than discovering these via a TLC counterexample (expensive).
