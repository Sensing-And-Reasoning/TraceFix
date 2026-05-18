# IR v3 Schema (PlusCal variant)

The IR defines the coordination topology with three arrays (no states — behavior is PlusCal):

## agents
```json
{"id": "coordinator"}
```
- `id`: unique identifier (becomes a PlusCal process)

## resources
```json
{"id": "db_lock", "type": "Lock"}
{"id": "api_pool", "type": "Counter", "config": {"initial": 5}}
```

| Type | Semantics | PlusCal macro |
|------|-----------|---------------|
| Lock | Exclusive access (binary) | `acquire_lock(lock)` / `release_lock(lock)` |
| Counter | Shared resource pool | `acquire_counter(ctr)` / `release_counter(ctr)` |

Counter models shared finite resources with limited capacity (API rate limits, connection pools, GPU slots). **NEVER use Counter for loop bounds, revision limits, or retry budgets.** Loops are unbounded state machine cycles — TLC handles them automatically.

## channels
```json
{"id": "coord_to_bankA", "from": "coordinator", "to": "bankA", "labels": ["prepare", "commit", "abort"]}
```
- `from`/`to`: agent(s) allowed to send/receive (string or array)
- `labels`: **required** — all message types on this channel
- PlusCal macros: `send(ch, "label")` / `receive(ch, var)` (var gets the label string)
- Channels are unbounded — send never blocks
- **Never create multiple channels between the same (from, to) pair** — use labels to distinguish message types

## Complete Example: Two-Phase Commit (2PC)

IR (agents, resources, channels — no states):
```json
{
  "agents": [
    {"id": "coordinator"},
    {"id": "workerA"},
    {"id": "workerB"}
  ],
  "resources": [
    {"id": "res_A", "type": "Lock"},
    {"id": "res_B", "type": "Lock"}
  ],
  "channels": [
    {"id": "to_A", "from": "coordinator", "to": "workerA", "labels": ["prepare", "commit", "abort"]},
    {"id": "to_B", "from": "coordinator", "to": "workerB", "labels": ["prepare", "commit", "abort"]},
    {"id": "from_A", "from": "workerA", "to": "coordinator", "labels": ["yes", "no"]},
    {"id": "from_B", "from": "workerB", "to": "coordinator", "labels": ["yes", "no"]}
  ]
}
```

PlusCal process bodies (what you write after scaffold):
```
fair process (coordinator_proc \in {Coordinator})
variables msg = "", voteA = "", voteB = "";
{
  c_send:
    send(to_A, "prepare");
    send(to_B, "prepare");

  c_wait_votes:
    either {
      c_rcv_A: receive(from_A, voteA);
      c_rcv_B1: receive(from_B, voteB);
    } or {
      c_rcv_B: receive(from_B, voteB);
      c_rcv_A1: receive(from_A, voteA);
    };

  c_decide:
    if (voteA = "yes" /\ voteB = "yes") {
      goto c_commit;
    } else {
      goto c_abort;
    };

  c_commit:
    send(to_A, "commit");
    send(to_B, "commit");
    goto c_done;

  c_abort:
    send(to_A, "abort");
    send(to_B, "abort");

  c_done:
    skip;
}

fair process (workerA_proc \in {WorkerA})
variables msg = "";
{
  a_idle:
    receive(to_A, msg);

  a_vote:
    either {
      acquire_lock(res_A);
      send(from_A, "yes");

    a_locked:
      receive(to_A, msg);
    a_handle:
      if (msg = "commit") {
      a_release_ok:
        release_lock(res_A);
      } else {
      a_release_abort:
        release_lock(res_A);
      };
    } or {
      send(from_A, "no");
    a_voted_no:
      receive(to_A, msg); (* drain commit/abort *)
    };
}

fair process (workerB_proc \in {WorkerB})
variables msg = "";
{
  b_idle:
    receive(to_B, msg);

  b_vote:
    either {
      acquire_lock(res_B);
      send(from_B, "yes");

    b_locked:
      receive(to_B, msg);
    b_handle:
      if (msg = "commit") {
      b_release_ok:
        release_lock(res_B);
      } else {
      b_release_abort:
        release_lock(res_B);
      };
    } or {
      send(from_B, "no");
    b_voted_no:
      receive(to_B, msg); (* drain commit/abort *)
    };
}
```

Key design decisions (this example demonstrates the PlusCal rules from [pluscal-guide.md](pluscal-guide.md)):
- **Either-order receives**: coordinator uses `either/or` at `c_wait_votes` so TLC explores both arrival orderings (A first vs B first)
- **if/else for message dispatch**: `c_decide` uses `if` to branch on vote values — NEVER use `assert` inside `either/or` for this
- **Lock lifecycle across labels**: workerA acquires `res_A` at `a_vote`, holds through `a_locked`, releases at `a_release_ok`/`a_release_abort`. The lock is genuinely held during the wait.

## End-to-End Walkthrough: Task 6E

This walkthrough shows the complete 5-phase workflow for Task 6E (Shared Utility File Conflict) — a simple 3-agent, 2-lock, 4-channel protocol that verified on the first attempt.

### Task Summary

Two developers (dev_a, dev_b) implement separate features that both modify a shared utility file in REPO. A reviewer approves or requests revisions before each feature can be merged. The protocol must ensure mutual exclusion on REPO and that all agents terminate.

### Phase 1: IR Design

Hazard analysis identifies: (1) race condition on shared utility file → `utility_lock`, (2) merge serialization → `merge_lock`, (3) developer→reviewer notification → 2 channels, (4) reviewer→developer feedback → 2 channels.

**`ir.json`**:
```json
{
  "agents": [
    {"id": "dev_a"},
    {"id": "dev_b"},
    {"id": "reviewer"}
  ],
  "resources": [
    {"id": "utility_lock", "type": "Lock"},
    {"id": "merge_lock", "type": "Lock"}
  ],
  "channels": [
    {"id": "ch_a_to_rev", "from": "dev_a", "to": "reviewer", "labels": ["code_ready"]},
    {"id": "ch_b_to_rev", "from": "dev_b", "to": "reviewer", "labels": ["code_ready"]},
    {"id": "ch_rev_to_a", "from": "reviewer", "to": "dev_a", "labels": ["approved", "revise"]},
    {"id": "ch_rev_to_b", "from": "reviewer", "to": "dev_b", "labels": ["approved", "revise"]}
  ]
}
```

Run: `tla-verify-pluscal scaffold ir.json` → generates `Protocol.tla` (stubs) + `Protocol.cfg`.

### Phase 2: PlusCal Process Bodies

Representative excerpt — `dev_a` process (dev_b is symmetric):
```
fair process (dev_a_proc \in {Dev_a})
variables msg = "";
{
  da_loop:
    while (TRUE) {
      da_acq:
        acquire_lock(utility_lock);
      da_work:
        skip; \* implement feature / revise code under lock
      da_rel:
        release_lock(utility_lock);
        send(ch_a_to_rev, "code_ready");
      da_wait:
        receive(ch_rev_to_a, msg);
      da_check:
        if (msg = "approved") {
          goto da_done;
        };
    };
  da_done:
    skip;
}
```

The reviewer uses `either/or` at `r_start` to nondeterministically choose which developer to review first, ensuring TLC explores both orderings.

### Phase 2.5: Semantic Fidelity Checklist

1. **Resource coverage**: utility_lock (shared file) + merge_lock (merge serialization) — PASS
2. **Channel coverage**: 4 channels match task's 2 code_ready + 2 feedback flows — PASS
3. **Ordering coverage**: receive guards enforce review-before-merge — PASS
4. **Per-agent behavior**: dev_a/dev_b: acquire→work→release→notify→wait→loop/done; reviewer: receive→review→approve/revise→merge — PASS
5. **Decision points**: reviewer either/or for approve vs revise — PASS
6. **Failure paths**: revise triggers retry loop back to da_loop/db_loop — PASS
7. **Collect-then-compare**: N/A (reviewer handles each developer independently) — PASS
8. **Work state labels**: da_work/db_work between acquire and release — PASS
9. **Naming consistency**: dev_a, dev_b, reviewer match task — PASS

### Phase 3: TLC Verification

Run: `tla-verify-pluscal verify .`

```
TLC passed — Model checking completed. No error.
  Distinct states found: 1,247
  States examined: 3,891
  0 errors, 0 warnings
  0 repairs needed
```

### Phase 4: Extract States

Run: `tla-verify-pluscal extract-states .` → produces `states.json`.

Excerpt — `dev_a` state machine (6 states):
```json
{
  "id": "da_loop", "agent": "dev_a",
  "actions": [{"next_state": "da_acq"}]
},
{
  "id": "da_acq", "agent": "dev_a",
  "actions": [{"next_state": "da_work", "acquire": "utility_lock"}]
},
{
  "id": "da_work", "agent": "dev_a",
  "actions": [{"next_state": "da_rel"}]
},
{
  "id": "da_rel", "agent": "dev_a",
  "actions": [{"next_state": "da_wait", "release": "utility_lock",
    "send": {"channel": "ch_a_to_rev", "label": "code_ready"}}]
},
{
  "id": "da_wait", "agent": "dev_a",
  "actions": [
    {"next_state": "da_done", "receive": {"channel": "ch_rev_to_a", "label": "approved"}},
    {"next_state": "da_loop", "receive": {"channel": "ch_rev_to_a", "label": "revise"}}
  ]
},
{
  "id": "da_done", "agent": "dev_a", "actions": []
}
```

Total: 26 states (6 dev_a + 6 dev_b + 14 reviewer), 3 initial states.

### Phase 5: Per-Agent Prompts

Excerpt — Runtime B prompt for `dev_a` (first 3 layers):
```markdown
# dev_a — Agent Prompt

## 1. Context
You are **dev_a** in a collaborative software development team.
Your role: Implement a user authentication feature...
Your position in the protocol:
  dev_a ──code_ready──→ reviewer ──approved/revise──→ dev_a

## 2. Coordination Protocol
### Shared Resources
- `utility_lock`: Exclusive access to the shared utility file.
### Communication Channels
You send: ch_a_to_rev → reviewer (labels: code_ready)
You receive: ch_rev_to_a ← reviewer (labels: approved, revise)

## 3. Step-by-Step Workflow
Step 1: Implement Feature
  Call acquire_lock("utility_lock")
  [domain work: implement user authentication]
  Call release_lock("utility_lock")
  Call send_message("ch_a_to_rev", "code_ready")
Step 2: Wait for Review
  Call receive_message("ch_rev_to_a")
  If "approved" → Step 3
  If "revise" → back to Step 1
Step 3: Done
  Call signal_done()
```

**Summary**: 3 agents, 2 locks, 4 channels, 26 states, 0 repairs. All artifacts generated: `ir.json`, `Protocol.tla`, `Protocol.cfg`, `states.json`, `prompts/runtime_a/`, `prompts/runtime_b/`.
