# PlusCal Process Body Guide

**What PlusCal models**: PlusCal models the coordination protocol only — the sequence of `acquire`/`release`/`send`/`receive` operations and decision branches (`if`/`either`). Domain work (tool calls, computations, business logic) is NOT modeled concretely. Where domain work occurs between coordination steps, use a `skip` label as a placeholder state. TLC verifies coordination properties (deadlock freedom, mutual exclusion), not business logic correctness.

Each agent process in Protocol.tla has this structure after scaffold:
```
fair process (agent_proc \in {AgentConst})
variables msg = "";
{
  agent_start:
    skip; (* TODO: replace with protocol logic *)
}
```

Replace the body with your PlusCal protocol logic.

## Key Syntax

**Labels** = atomic steps. A label MUST appear:
- Before every `receive` or `acquire_lock`/`acquire_counter` (blocking operations)
- Before a `goto`
- At the start of each process body
- Labels must be globally unique across ALL processes

**either/or** = nondeterministic choice (TLC explores all branches):
```
decide:
  either {
    send(ch, "approve");
    goto approved;
  } or {
    send(ch, "reject");
    goto rejected;
  };
```

**while** = loops (unbounded — TLC handles via ChannelBound):
```
review_loop:
  while (TRUE) {
    wait_sub:
      receive(submission_ch, msg);
    evaluate:
      either {
        send(feedback_ch, "accept");
        goto done;
      } or {
        send(feedback_ch, "revise");
        (* loops back to wait_sub *)
      };
  };
```

**Failure recovery loop** = test/validate with retry on failure:
```
dev_loop:
  while (TRUE) {
    d_do_work:
      acquire_lock(shared_res);
    d_work:
      skip; (* implement feature under lock *)
    d_release:
      release_lock(shared_res);
      send(to_reviewer, "submit");
    d_wait_review:
      receive(from_reviewer, msg);
    d_check_review:
      if (msg = "approve") {
        goto d_request_test;
      } else {
        goto d_do_work;  (* revise and re-submit *)
      };
  };
d_request_test:
  send(to_tester, "test");
d_wait_test:
  receive(from_tester, msg);
d_check_test:
  if (msg = "pass") {
    goto d_done;
  } else {
    goto dev_loop;  (* fail → re-implement → re-review → re-test *)
  };
d_done:
  skip;
```

**Macros available** (defined in the scaffold):
- `send(ch, msg)` — append msg to channel (never blocks)
- `receive(ch, var)` — blocks until channel non-empty, pops head into var
- `acquire_lock(lock)` — blocks until lock is FREE, sets to self
- `release_lock(lock)` — sets lock to FREE
- `acquire_counter(ctr)` — blocks until counter > 0, decrements
- `release_counter(ctr)` — increments counter

## Work State Labels

Every `acquire_lock`→`release_lock` pair must have at least one intermediate PlusCal label between them. Without it, TLC treats the acquire and release as adjacent atomic steps with no work in between — and in Runtime A, the domain work (Phase 2) executes *before* the lock is acquired (Phase 3), meaning the critical section is empty.

**When NOT needed:** If a `receive`, `send`, `if`, or `either` statement already appears between acquire and release (each requiring its own label), no extra `skip` is needed — those labels already serve as intermediate work states.

**Pattern A — Simple critical section:**
```
  acq:
    acquire_lock(res);
  work:
    skip; (* domain work happens here under the lock *)
  rel:
    release_lock(res);
```

**Pattern B — Multiple locks (nested):**
```
  acq_outer:
    acquire_lock(res_a);
  acq_inner:
    acquire_lock(res_b);
  work:
    skip; (* domain work under both locks *)
  rel_inner:
    release_lock(res_b);
  rel_outer:
    release_lock(res_a);
```

**Pattern C — Coordination as intermediate (no extra skip needed):**
```
  acq:
    acquire_lock(res);
  recv:
    receive(ch, msg);  (* this label IS the intermediate work *)
  rel:
    release_lock(res);
```

## PlusCal Rules

1. **Label before every blocking op**: `receive`, `acquire_lock`, `acquire_counter` need a label on or before them
2. **Globally unique labels**: no two processes can share a label name. Prefix with agent name (e.g., `coord_wait`, `workerA_vote`)
3. **No labels inside macros**: macros (send/receive/acquire/release) cannot contain labels
4. **`self` is handled automatically**: `acquire_lock(lock)` internally uses `self` to set the lock owner
5. **Terminal state**: when a process reaches the closing `}`, it enters state "Done"
6. **Either-order receives**: use `either { receive(chA, msg) } or { receive(chB, msg) }` for nondeterministic arrival order
7. **Semicolons**: every statement ends with `;` — including the last one before `}`
8. **Labels are sequential — fall-through is the default**: After executing the code at label X, execution continues to the NEXT label in source order, NOT back to a loop head or branch point. If you use `goto` to jump to a label for case-handling, you MUST add an explicit `goto` at the end of that case to return to the loop head. Otherwise execution falls through to the next label below:
```
  (* WRONG — after handling case_a, falls through to case_b *)
  choose: if (...) { goto case_a; } else { goto case_b; };
  case_a: ... handle A ...;
  case_b: ... handle B ...;  (* ALSO executes after case_a! *)

  (* CORRECT — explicit goto back to loop *)
  choose: if (...) { goto case_a; } else { goto case_b; };
  case_a: ... handle A ...; goto loop_head;
  case_b: ... handle B ...; goto loop_head;
```

## PlusCal Error Patterns

**Missing label before blocking op**:
```
  send(ch, "go");
  receive(ch2, msg);  (* ERROR: needs a label before receive *)
```
Fix: add a label like `wait_reply: receive(ch2, msg);`

**Duplicate label**:
```
  start: skip;   (* in process A *)
  start: skip;   (* in process B — ERROR: duplicate *)
```
Fix: use unique prefixes: `a_start:` and `b_start:`

**Missing semicolon**:
```
  either { send(ch, "yes") } or { send(ch, "no") }
```
Fix: add `;` after each statement and after the `or` block

**Goto to wrong label**: goto targets must be labels in the SAME process

**Assert inside either/or** (TLC will always fail):
```
  either { assert msg = "yes"; } or { assert msg = "no"; };
```
Fix: use `if (msg = "yes") { ... } else { ... };` for message dispatch

**Accept branch falls through to revision code**:
```
  either { skip; (* accept — but falls through! *) }
  or { skip; (* revise *) };
  revision_start:  (* BOTH branches reach here *)
    acquire_lock(res);
```
Fix: add `goto a_done;` in the accept branch to skip past revision code

**Goto-based branching without return goto** (causes deadlock):
```
  choose: if (...) { goto handle_a; } else { goto handle_b; };
  handle_a:
    receive(ch_a, msg);
    ... process a ...
    (* MISSING goto loop; — falls through to handle_b! *)
  handle_b:
    receive(ch_b, msg);  (* deadlock: blocks even after handling a *)
```
Fix: add `goto loop;` after each case handler to return to the loop head

**Collect-then-compare** — process multiple inputs before deciding:
```
  (* WRONG — processes proposals independently, no conflict detection *)
  arch_loop:
    either {
      a_rcv_A: receive(devA_ch, msg);
      a_decide_A: either { approve A } or { reject A };
    } or {
      a_rcv_B: receive(devB_ch, msg);
      a_decide_B: either { approve B } or { reject B };
    };

  (* CORRECT — collects both in either order, then decides with full context *)
  a_collect:
    either {
      a_rcv_A_first: receive(devA_ch, msgA);
      a_rcv_B_second: receive(devB_ch, msgB);
    } or {
      a_rcv_B_first: receive(devB_ch, msgB);
      a_rcv_A_second: receive(devA_ch, msgA);
    };
  a_decide:
    either {
      send(arch_to_devA, "approve");
      send(arch_to_devB, "approve");
    } or {
      send(arch_to_devA, "approve");
      send(arch_to_devB, "reject");
    } or {
      send(arch_to_devA, "reject");
      send(arch_to_devB, "approve");
    } or {
      send(arch_to_devA, "reject");
      send(arch_to_devB, "reject");
    };
```

## TLC Error Patterns and Fixes

### Deadlock
The system reached a state where no agent can make progress.
Common causes:
- **Circular resource dependency**: Fix with consistent lock acquisition order
- **Missing message**: Ensure every receive has a corresponding send path
- **Counter at zero**: Ensure release paths exist before acquire points

### Safety Violation (MutualExclusion)
Two agents hold the same Lock simultaneously.
Fix: ensure every acquire has a matching release on ALL paths.

### Note on Liveness and Loops
TLC does NOT check liveness properties — only safety: deadlock freedom, type invariants, no orphan locks, channel drainage. Because liveness is not checked, loops do NOT need to be bounded.
