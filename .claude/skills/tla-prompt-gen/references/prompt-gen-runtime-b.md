# Runtime B Prompt Generation (Agent-Driven)

In Runtime B, agents are autonomous — they explicitly call coordination tools (`acquire_lock`, `release_lock`, `send_message`, `receive_message`, `poll_channels`, `receive_any`) alongside domain tools.

## Prompt Structure (3 Layers)

```
Layer 1: Context        — Who you are, system overview, protocol topology
Layer 2: Protocol       — Shared resources, communication channels, critical rules
Layer 3: Workflow       — Step-by-step with coordination + domain tools interleaved
```

**Note on tools**: Do NOT include a `## Tools` section in the prompt. The runtime provides all tool schemas (domain + coordination) to the LLM via function calling. The prompt only needs to reference tool names in the workflow steps — the LLM gets the full signatures and descriptions automatically.

## Layer 1: Context

Provide three things:

1. **Role**: One sentence describing the agent's function
2. **System overview**: Who else is in the system, what they do, how the agent relates to them
3. **Protocol topology**: ASCII diagram showing the agent's message flows

Example:
```markdown
## 1. Context

You are **researcherA** in a collaborative paper-writing team.

**Your role**: Research and write a section on subtopic A, submit for
fact-checking and editorial review, revise if needed.

**System overview**: You work alongside researcherB (subtopic B),
a factchecker (verifies claims), and an editor (ensures cross-section
consistency). You and researcherB work in parallel but share access
to the document draft and reference database.

**Your position in the protocol**:
  researcherA ──submit──→ factchecker ──pass/flag──→ researcherA
  researcherA ──resubmit─→ editor ──accept/revise──→ researcherA
```

## Layer 2: Coordination Protocol

List all coordination primitives the agent uses, then the rules.

### Shared Resources

For each resource the agent acquires/releases:
```markdown
- `doc_lock`: Exclusive access to the shared document draft.
  You and researcherB both write to this — always acquire before
  writing, release immediately after.
```

### Communication Channels

Split into send and receive, with labels:
```markdown
**You send:**
- `resA_to_fc` → factchecker (labels: submit)

**You receive:**
- `fc_to_resA` ← factchecker (labels: pass, flag)
```

### Critical Rules

Derive from IR and PlusCal by scanning for these patterns:

| Source | Rule to extract |
|---|---|
| **Always (every agent)** | "Follow the workflow steps below **EXACTLY** in this order. Do NOT skip steps, reorder operations, or improvise alternatives. If a coordination call returns `\"timeout\"`, retry it immediately — never proceed to the next step without completing the current one." |
| Agent uses a Lock | "Always acquire `{lock}` before {action}, release immediately after" |
| Agent acquires multiple locks | "Always acquire in fixed order: `{lock1}` then `{lock2}` (prevents deadlock with other agents)" |
| Multiple acquires before a critical operation | "Hold all required locks before {operation} — do not start until all are acquired" |
| Multiple releases after a critical operation | "Release in reverse order of acquisition: `{lockN}` then ... then `{lock1}`" |
| Domain work after all releases | "Run {post-work} only after releasing all locks — do not block other agents while doing non-critical work" |
| Agent uses a Counter | "Call `acquire_lock` before using {resource}, `release_lock` after" (Runtime B uses `acquire_lock`/`release_lock` for both locks and counters) |
| `receive` followed by `if/else` | "After receiving on `{channel}`, check the label and follow the matching branch" |
| `if (msg = "accept") { goto done }` | "After receiving 'accept', go directly to Done — do not execute further steps" |
| `while(TRUE)` with retry | "If {condition}, loop back to Step N to retry" |
| Any `receive_message` call | "Do not skip a receive — keep retrying until a message arrives" |
| `goto done` in one branch of `either/or` | "The {branch} path terminates the workflow — do not fall through to other steps" |
| `either/or` with all `recv` branches | "Use `receive_any` to wait on all channels simultaneously — do not try each channel sequentially" |
| `either/or` with mixed `recv` + `send`/`goto` | "Use `poll_channels` to check for pending messages — if none, take the non-blocking action" |
| `receive_any` result | "Check the `channel` field in the response to determine which sender responded" |

Generate 3-6 rules per agent in this priority order:

0. **Protocol adherence rule (MANDATORY — always the first rule, verbatim)**:
   "Follow the workflow steps below **EXACTLY** in this order. Do NOT skip steps, reorder operations, or improvise alternatives. If a coordination call returns `"timeout"`, retry it immediately — never proceed to the next step without completing the current one."
1. Multi-lock ordering rules (prevents deadlock)
2. Termination rules (when and how to reach Done)
3. Retry/recovery loop rules (when to loop back)
4. Lock discipline rules (acquire/release pairing)
5. Message handling rules (retry on receive, label checking)
6. Counter rules (acquire/release capacity)

**If repairs were needed** (check `summary.json`), boost rules that prevent the encountered error types.

## Layer 3: Workflow

Step-by-step instructions with coordination and domain tools interleaved.

### PlusCal Translation Rules

| PlusCal construct | Natural language |
|---|---|
| `acquire_lock(X)` | "Call `acquire_lock("X")`. If `"timeout"`, retry immediately — do NOT proceed to the next step without holding the lock." |
| `release_lock(X)` | "Call `release_lock("X")` — release X" |
| `acquire_counter(X)` | "Call `acquire_lock("X")`. If `"timeout"`, retry immediately — do NOT proceed to the next step without holding the resource." (Runtime B uses `acquire_lock` for both locks and counters) |
| `release_counter(X)` | "Call `release_lock("X")` — return one unit of capacity to X" (Runtime B uses `release_lock` for both locks and counters) |
| `send(ch, "label")` | "Call `send_message("ch", "label")` — notify [recipient] that [meaning]" |
| `receive(ch, msg)` | "Call `receive_message("ch")`. If `"timeout"`, retry immediately — do NOT proceed to the next step without receiving a message." |
| `if (msg = "X") { goto Y } else { goto Z }` | "**Decision Point:** If response is `"X"`, go to Step N; otherwise go to Step M" |
| `if (msg = "X") { goto Y };` (no else) | "**Decision Point:** If response is `"X"`, go to Step N. Otherwise continue to next step." |
| `either/or` (all branches `recv`) | "Call `receive_any([ch_a, ch_b])` — waits for a message from any channel. Check which channel responded." |
| `either/or` (some `recv`, some `send`/`goto`) | "Call `poll_channels([ch_a])` — non-blocking check. If `"received"`, handle it. If `"none"`, proceed with the always-available action." |
| `either/or` (no `recv` — pure judgment) | "**Nondeterministic Choice:** Based on your judgment, choose one: (a) ... (b) ..." |
| `while(TRUE) { ... }` | Wrap the loop body steps, then add "Go back to Step N" at the end |
| `goto label` | "Go to Step N" |
| Process end | "Call `signal_done()` — you are DONE." |

> **Tool selection from `states.json`**: When `states.json` includes `tool_hint` for a state, use it directly. When writing without `states.json`, derive the hint: all actions have `receive` → `receive_any`; some actions have `receive`, others don't → `poll_channels`; no actions have `receive` → LLM judgment.

### Label-to-Step Consolidation

> **MANDATORY**: Before writing any prompt steps, build a Label-to-Step Mapping table using `states.json` as ground truth (see the researcherA example below). Every state must appear in exactly one row. Use `tool_hint` from `states.json` to select the correct coordination tool.

PlusCal labels do NOT map 1:1 to prompt steps. Apply these rules:

| Pattern | Consolidation |
|---|---|
| **acquire + work + release** | One step: "Acquire X, do work, release X". If the work state has a `task` field, render it as the step's **Work:** line (see "Business task vs coordination" below) |
| **acquire + `skip` work state + release** | One step: "Acquire X, do work, release X" (the `skip` label is a work-state placeholder — absorb it into the acquire/release step). If that work state carries a `task`, use it verbatim as the **Work:** line |
| **receive + if/else dispatch** | One step with Decision Point |
| **sequential sends** | One step if no receive between them |
| **release + immediate send** | Merge into preceding step |
| **label with only `skip`** | Terminal step: "Done" |
| **label with only a goto** | Omit — fold into preceding Decision Point |
| **`either/or` with all `recv` branches** | One step: "Wait for any message via `receive_any`" + channel-dispatch |
| **`either/or` with mixed `recv` + always-enabled** | One step: "Check for messages via `poll_channels`, if none → {default action}" |

**Guideline**: Consolidation merges adjacent labels into one semantic step (e.g., acquire + work + release → one step), but the order of steps MUST match the PlusCal control flow. Do NOT reorder steps by semantic grouping — the execution sequence is determined by the PlusCal process body.

### Business task vs coordination (the `task` field)

`states.json` may carry a `task` field on a state — a short description of the BUSINESS work to do there (from the IR's optional `state_tasks`). This is the **data-plane** work, distinct from the **control-plane** coordination calls. Make that separation explicit in the prompt so the agent understands the two are different concerns: coordination calls are its obligations to OTHER agents; the `task` is its own domain work to perform *at that state*.

When a state has a `task`, render the step with two labeled lines:

> ### Step 3: Write your section
> **Work (business):** {state's `task` verbatim — e.g. "read research.md, append your section, preserve all existing content"}
> **Coordinate (control):** `acquire_lock("DOC")` before you start, `release_lock("DOC")` when done.

Notes:
- `task` is advisory / observability only — it NEVER changes the coordination contract, the step order, or the verified model. If a state has no `task`, describe the work from the task description as before.
- Optionally remind the agent it may call `report_progress(label)` to announce finer sub-steps within a long business task (pure telemetry; never required).

### Domain Tool Integration

Domain tools go at specific positions relative to coordination calls:

| Position | When to use |
|---|---|
| **Between acquire and release** | Agent does work while holding a shared resource |
| **After receive, before send** | Agent processes received input then responds |
| **Before first coordination call** | Agent does independent prep work |

If a tool has `"can_fail": true`, describe both outcomes (maps to `either/or` in PlusCal).

### Channel-Dispatch Domain Tool Parameters

When an `either/or` receives from different channels and then calls the same domain tool, the tool parameters should vary based on which channel the message came from. Consult `tools.json` for the parameter descriptions and valid values, and the task description for the semantic mapping.

Example — metrology engineer receives from 3 channels, each requiring a different measurement:
```markdown
#### Step 1: Wait for a notification
Call `receive_any(["litho_to_metro", "depo_to_metro", "etch_to_metro"])`.
Note which channel the message came from.

#### Step 2: Measure (based on source)
- If received from `litho_to_metro`: Call `run_metrology_measurement(measurement="cd_measurement")`
- If received from `depo_to_metro`: Call `run_metrology_measurement(measurement="thickness_measurement")`
- If received from `etch_to_metro`: Call `run_metrology_measurement(measurement="profile_measurement")`
```

Do NOT hardcode a single parameter value when the receive source distinguishes which action to take.

## Template

Use this structure for each `prompts/runtime_b/{agent_id}.md`:

~~~markdown
# {Agent ID} — Agent Prompt

## 1. Context

You are **{agent_id}** in a multi-agent system.

**Your role**: {one-sentence role description}

**System overview**: {who else is in the system, how you relate to them}

**Your position in the protocol**:
```
{ASCII topology diagram showing this agent's message flows}
```

## 2. Coordination Protocol

### Shared Resources
- `{lock_id}`: {what it protects}. {which agents compete for it}.
...

### Communication Channels

**You send:**
- `{channel_id}` → {partner_agent} (labels: {label1, label2, ...})
...

**You receive:**
- `{channel_id}` ← {partner_agent} (labels: {label1, label2, ...})
...

### Critical Rules
1. {rule}
2. ...

## 3. Workflow

### Step 1: {Step Name}
{description with domain + coordination tool calls}

### Step 2: {Step Name}
...

**Decision Point:**
- If you receive **"{label_a}"**: {action}
- If you receive **"{label_b}"**: {action}

...

### Step N: Done
Call `signal_done()` — you are DONE.
~~~

## Verification Checklist (MANDATORY)

After generating each agent's prompt, verify it against `states.json`:

| Check | How | Fail → |
|---|---|---|
| All states covered | Every state ID for this agent in `states.json` appears in mapping table | Add missing state |
| All branches covered | State with N actions → prompt has N branches | Add missing branch |
| Channel IDs exact | `send`/`receive` channel in `states.json` matches prompt tool arg | Fix ID |
| Lock IDs exact | `acquire`/`release` resource in `states.json` matches prompt tool arg | Fix ID |
| Labels exact | `send` label in `states.json` matches `send_message()` label arg | Fix label |
| Tool selection | `tool_hint: receive_any` → `receive_any`; `poll_channels` → `poll_channels` | Switch tool |
| Terminal | Last step has `signal_done()` | Add it |
| Step order faithful | Prompt step order matches PlusCal process body control flow (initial state → execution order) | Reorder steps |
| No phantom ops | No coord calls in prompt that aren't in `states.json` | Remove |

## Example: researcherA in task 3M

### Label-to-Step Mapping

| PlusCal Labels | Prompt Step | Consolidation Rule | Coordination Calls |
|---|---|---|---|
| `ra_write` + `ra_rel_doc` | Step 1: Write Draft | acquire + work + release | acquire_lock("doc_lock"), release_lock("doc_lock") |
| `ra_ref` + `ra_rel_ref` + send | Step 2: Update References & Submit | acquire + work + release + send | acquire_lock("ref_lock"), release_lock("ref_lock"), send_message("resA_to_fc", "submit") |
| `ra_wait_fc` + `ra_check_fc` | Step 3: Wait for Fact Check | receive + if/else dispatch | receive_message("fc_to_resA") |
| `ra_wait_ed` + `ra_check_ed` | Step 4: Wait for Editorial Review | receive + if/else dispatch | receive_message("editor_to_resA") |
| `ra_revise` + `ra_rev_rel` + send | Step 5: Revise for Consistency | acquire + work + release + send | acquire_lock("doc_lock"), release_lock("doc_lock"), send_message("resA_to_editor", "resubmit") |
| `ra_wait_ed2` | Step 6: Wait for Final Decision | standalone receive | receive_message("editor_to_resA") |
| `ra_done` | Step 7: Done | terminal skip | signal_done() |

### Generated Prompt

~~~markdown
# researcherA — Agent Prompt

## 1. Context

You are **researcherA** in a collaborative paper-writing team.

**Your role**: Research and write a section on subtopic A, submit for fact-checking and editorial review, revise if needed.

**System overview**: You work alongside researcherB (subtopic B), a factchecker (verifies claims), and an editor (ensures cross-section consistency). You and researcherB work in parallel but share access to the document draft and reference database.

**Your position in the protocol**:
```
researcherA ──submit──→ factchecker ──pass/flag──→ researcherA
researcherA ──resubmit─→ editor ──accept/revise──→ researcherA
```

## 2. Coordination Protocol

### Shared Resources
- `doc_lock`: Exclusive access to the shared document draft. You and researcherB both write to this — always acquire before writing, release immediately after.
- `ref_lock`: Exclusive access to the reference database.

### Communication Channels

**You send:**
- `resA_to_fc` → factchecker (labels: submit)
- `resA_to_editor` → editor (labels: resubmit)

**You receive:**
- `fc_to_resA` ← factchecker (labels: pass, flag)
- `editor_to_resA` ← editor (labels: accept, revise)

### Critical Rules
1. Lock ordering: always acquire `doc_lock` before `ref_lock` if you ever need both (prevents deadlock with researcherB).
2. Always acquire `doc_lock` before writing or revising your section, and release it immediately after.
3. After receiving "accept" from the editor, go directly to Done — do not execute any more steps.
4. After receiving "flag" from the fact checker, you must revise and resubmit — do not skip the revision.
5. Do not proceed past a receive until you get a response — if you get `"timeout"`, retry the same `receive_message` call.

## 3. Workflow

### Step 1: Write Draft
- Call `research_topic(topic="subtopic A")` to gather sources
- Call `acquire_lock("doc_lock")` — waits until the document draft is available
- Call `write_section(section_name="section A")` to write your draft
- Call `release_lock("doc_lock")` — release the document

### Step 2: Update References & Submit
- Call `acquire_lock("ref_lock")` — waits until the reference database is available
- Call `update_references(section_name="section A")`
- Call `release_lock("ref_lock")` — release the reference database
- Call `send_message("resA_to_fc", "submit")` — submit your section to the Fact Checker

### Step 3: Wait for Fact Check
- Call `receive_message("fc_to_resA")` — wait for the Fact Checker's verdict

**Decision Point:**
- If you receive **"flag"** (claims unverifiable): Go back to **Step 1** and revise
- If you receive **"pass"** (claims verified): Continue to **Step 4**

### Step 4: Wait for Editorial Review
- Call `receive_message("editor_to_resA")` — wait for the Editor's decision

**Decision Point:**
- If you receive **"accept"** (section approved): Go to **Step 7 (Done)**
- If you receive **"revise"** (cross-section inconsistencies): Continue to **Step 5**

### Step 5: Revise for Consistency
- Call `acquire_lock("doc_lock")` — waits until the document draft is available
- Call `revise_section(section_name="section A", feedback="editor: cross-section inconsistency")`
- Call `release_lock("doc_lock")` — release the document
- Call `send_message("resA_to_editor", "resubmit")` — notify the Editor

### Step 6: Wait for Final Decision
- Call `receive_message("editor_to_resA")` — wait for the Editor's final acceptance

### Step 7: Done
Call `signal_done()` — you are DONE.
~~~
