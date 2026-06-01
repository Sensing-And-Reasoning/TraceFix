# TraceFix Improve Plan

Status: design doc · 2026-05-31
Scope: answers to 11 design questions across the 4 pipeline stages, 3 locked decisions,
and 2 fleshed-out designs ready to implement.

---

## 0. Framing

TraceFix turns a natural-language coordination task into a TLA+-verified protocol, then
into per-agent prompts that LLM agents execute under a runtime monitor. The pipeline:

```
(1) user input  →  (2) protocol generation  →  (3) per-agent prompts  →  (4) runtime + monitor
   task prose         IR → PlusCal → TLC          states.json → prompt        agents act, monitor validates
```

**One principle answers most of these questions — the control/data-plane split:**

| Plane | Carries | Verified? | Monitored? | Lives in |
|---|---|---|---|---|
| **Control** | coordination: acquire/release/send/receive/signal_done; channel *labels* only | yes (TLC) | yes (monitor) | IR / PlusCal / states.json |
| **Data** | domain content (documents, payloads, results) | no | no | shared file / object store |

And one artifact is the **spine**: the **per-agent step machine** appears (after this plan)
in four places — the review draft (2.1), `states.json` (ground truth), the prompt (3.2),
and the monitor's source of legal actions (4.3).

Two further rules of thumb recur:
- **Model coordination *consequences*, not domain internals.** (decides 2.2 and 2.3)
- **`states.json` is the single source of truth for coordination** — it drives prompts *and*
  runtime detection + correction.

Evidence base for the friction items below: a real custom (non-benchmark) task was run
end-to-end through the `/tla-verify-pluscal` skill — see
`tracefix.pipeline/custom_demo/hotfix/FRICTION_LOG.md`. Headline: **the verify skill is NOT
benchmark-locked** (a 3-agent "emergency hotfix" protocol verified first try, full closed
loop, zero benchmark, zero external API). The real benchmark coupling is downstream, in the
`tools.json` contract (F6).

---

## Stage 1 — User Input

### 1.1 What information must the user provide? *(open; layered answer)*

- **Required:** task prose + the list of agents (who acts concurrently) + the shared
  resources (what they contend over).
- **Strongly recommended:** each agent's domain-action list + a `can_fail` flag per action
  (the flag directly drives the failure branches in 2.2).
- The system should **extract the structured parts (a hazard table) from the prose and echo
  them back for confirmation** — the user should not hand-write the IR.
- **Suitability filter:** if there is no shared mutable state and no ordering dependency
  (embarrassingly parallel), there is nothing to verify — TraceFix adds no value. The input
  must reveal whether genuine coordination hazards exist; this is a gate, not just metadata.

### 1.2 How detailed must the problem be? *(already has a good template)*

Detailed enough to identify four things: **concurrent actors, shared resources + who touches
them, ordering constraints, and failure modes that need recovery.** NOT detailed enough to
specify PlusCal — that is TraceFix's job. The benchmark `description.md` files are the right
altitude. Best practice: after reading the description, **echo the hazard table and let the
user confirm/correct before generating the IR** — this is both early under-specification
capture and the suitability check from 1.1.

---

## Stage 2 — Protocol Generation

### 2.1 Text-first or PlusCal-first? → **DECISION: add a reviewable draft layer**

Source of truth **must be PlusCal** (it is what TLC checks); a text-primary / PlusCal-derived
design would drift during repair. But insert a **reviewable "coordination plan"** between
hazard analysis and PlusCal so semantic errors are caught before the expensive PlusCal+TLC
round. The authoritative text (prompts) is always *derived from the verified `states.json`*,
so it cannot drift. Full design in **Design A** below.

### 2.2 Should failure/retry be modeled as TLA+ states? Is it in TLC's scope? *(conditional)*

**Yes — but only when the failure/recovery changes the coordination structure** (re-acquires
a lock, re-sends a message, changes who-waits-for-whom, introduces a new interleaving). These
are the **most dangerous interleavings** (recovery-time deadlocks, re-contention) and exactly
where coordination verification adds the most value (cf. SKILL.md anti-pattern #9).

Rules:
- Model failure as a **nondeterministic `either/or` branch + `goto` loop**, NOT as a
  "did the domain op succeed?" boolean (that is unbounded domain state → state explosion).
- A domain-internal retry that does **not** touch coordination (retry the same SQL) is left to
  the runtime/domain layer, abstracted as a single `skip` — not modeled.
- **Model the coordination *consequence* of failure, not the failure itself.**

### 2.3 Should the protocol include domain tools? *(already correct; links to F6)*

The protocol **references** domain tools (name + `can_fail`, as annotations on `skip` states)
but does **not model** their semantics (TLC neither can nor should verify business logic).
Why the reference is needed:
1. the `skip` position decides whether the lock is held during the domain work (anti-pattern #11);
2. `can_fail` decides whether that `skip` needs an `either/or` failure branch — **this is the
   2.3 ↔ 2.2 hinge**;
3. it feeds prompt generation.

The tool vocabulary (name / params / `can_fail`) belongs in a **separate, first-class contract**
(`tools.json`) — see the cross-cutting "tools contract" item; this is the F6 generalization.

---

## Stage 3 — Per-agent Prompts

### 3.1 How detailed should a prompt be? *(architecture-dependent; control/data split)*

Runtime A (enforcement, engine-driven): prompts can be lighter. Runtime B (monitoring,
agent-driven): prompts must be detailed. Principle: **strict contract on the coordination
plane** (exact tool calls, order, channel/label IDs, branch-on-received-label) and **open
brief on the domain plane** (what to produce, not a script). Too detailed → the agent is a
mere executor (defeats using an LLM); too loose → the agent improvises coordination and
violates the protocol. "As detailed as `states.json` on coordination, as open as the task
allows on domain."

### 3.2 What must a prompt contain? *(has a skeleton; one addition)*

1. Identity & role; 2. Topology (send/receive to whom, what is shared); 3. **Coordination
contract** — `states.json` rendered as ordered steps (each step's coordination call with exact
IDs + domain placeholder + branch conditions) — the core; 4. Domain tool list + when to call
(with params, from the tools contract); 5. **Safety properties as imperatives** ("never write
DOC without holding doc_lock"); 6. Failure/recovery handling (from the failure branches);
7. Termination (when to `signal_done`).
**Addition: include the *why* (the hazard each step prevents)** — an agent that understands
"the lock prevents concurrent writes corrupting the doc" recovers better at the edges (links
to 4.3). Completeness depends on the tools contract (no `tools.json` → can't fill domain params; F6).

---

## Stage 4 — Runtime Monitoring

### 4.1 Monitor coordination logic only *(already the design)*

The monitor validates coordination operations against the IR topology whitelist + the state
machine; it does **not** monitor domain work (no spec to check it against, and "correct domain
output" is undecidable in general). Flag-only channels keep the coordination stream clean and
the domain payload off the monitored path.

### 4.2 Ensuring coordination is correct — reference the state map *(already the design; two levels)*

- **ProtocolMonitor** (topology whitelist): may this agent ever do this action?
- **StateTracker** (state machine vs `states.json`): is this action legal *right now* given the
  agent's current state? — the stronger guarantee (catches out-of-order coordination).

`states.json` is the verified ground truth (extracted from the TLC-passed protocol), so
validating against it *is* enforcing the verified protocol. Use the state-machine level.

### 4.3 Helping an agent back on track → **DECISION: monitoring correction (reject + guide)**

Default to **monitoring (B) with correction**, not enforcement (A). When an agent makes an
illegal coordination call: reject it, diagnose why, and return the **legal next action(s) from
`states.json`** plus situational context; bound the retries and **fail honestly** if the agent
can't recover. Full design in **Design B** below.

### 4.4 Domain info exchange between agents → **DECISION: parked**

Already solved in `sdk_adapter` via the control/data split (Claim-Check): the coordination
channel carries a label/pointer; the domain content is written to a shared medium (file/store)
protected by the same lock the protocol verified, written-before-signal / read-after-receive.
If the shared content is contended, model it as a Lock in the IR so the protocol orders access
to it. **Parked for now;** revisit the pluggable data-plane substrate (local file → shared mount
→ object store) when the distributed runtime (Phase 2) needs it.

---

## Design A — Coordination Plan (the reviewable draft layer) [decision 2.1]

**What it is.** A per-agent step outline generated *after* hazard analysis and *before* PlusCal,
human-readable without TLA+ knowledge:

```
Agent: DBA
  shares:  PROD_DB (lock)
  listens: oncall_to_dba(migrate)    notifies: dba_to_oncall(migrated)
  steps:
    1. wait "migrate" ← ONCALL                       [receive]
    2. acquire PROD_DB                               [lock]
    3. apply_migration()                            [domain]
    4. verify_schema()                              [domain, can_fail]
         ├─ clean  → 5
         └─ failed → rollback_migration(); apply_migration(); back to 4   [retry loop]
    5. release PROD_DB; send "migrated"             [unlock + signal]
    6. done
```

**Where it sits.** New **Phase 1.5** in the skill workflow (hazard → IR → **plan** → review →
PlusCal → verify). New artifact: `plan.md` (review surface), optionally `plan.json` (structured).

**Who reviews.** Skill version → **human confirms/corrects** (the highest-value check; SKILL.md
says semantic fidelity is the most common quality issue). Agent version → **critic-LLM
self-review** of the plan against `description.md`.

**What it prevents.** (1) Semantic infidelity (wrong topology, missing failure path, wrong
order) caught *before any TLA+ is written*; (2) wasted PlusCal+TLC cycles.

**Bonus.** If the plan is structured (typed steps: coordination / domain / branch), PlusCal can
be generated **near-mechanically** instead of free-written — which **removes the PlusCal
syntax-error failure mode** (the original 3E pipeline run died exactly there).

**Scope.**
- **v1 (light):** prose/table plan + human confirm; PlusCal still hand-written. Gets the review
  benefit, small change (mostly a SKILL.md Phase 1.5 + a `plan.md` convention).
- **v2 (heavier):** define a `plan.json` schema + a `plan → PlusCal` generator in
  `tracefix/pipeline/pipeline/`. Gets the "fewer syntax errors" benefit.

**Touches.** `.claude/skills/tla-verify-pluscal/SKILL.md` (+ Phase 1.5); v2 also
`tracefix/pipeline/pipeline/pluscal_generator.py` (or a new `plan_compiler.py`).

---

## Design B — Monitoring Correction (reject + guide + bounded fail) [decision 4.3]

**Mechanism.** When an agent calls an illegal coordination tool, the monitor:
1. **Rejects** (no coordination-state mutation) — already happens.
2. **Diagnoses:** topology ("you are not the sender of channel X") / state ("you called send(Y)
   but at your current state you must first receive(Z)") / resource ("you don't hold lock L").
3. **Guides:** include the **legal next action(s) at the agent's current state**, from
   `states.json` — *"At state `DBA_acquire`, the only legal action is acquire_lock(PROD_DB)."*
4. **Situational context:** *"channel oncall_to_dba has 1 unread message — receive it first."*
5. **Bounded retries → honest failure:** after N corrections at the same state with no progress,
   mark the agent failed and fail the run. **Never loop forever; never fake success** (consistent
   with the earlier-rejected "give-up hint" that pretended completion).

**Key design choice.** Promote state violations from **soft-recorded** to **blocking + corrective**,
forcing the agent back onto the verified path. Safe because `states.json` enumerates *all* legal
transitions (both `either` branches — e.g. `DBA_verify` has 2 `next_state`s), so blocking won't
wrongly reject a legal nondeterministic action.

**Where it lives (concrete hooks).**
- `tracefix/runtime/monitoring/state_tracker.py` — add `legal_actions(agent)` (a thin query over
  the `actions/next_state` already in `states.json`). **Detection (4.2) and guidance (4.3) share
  this one method.**
- `tracefix/runtime/sdk_adapter/dispatch.py` (and monitoring `coord.py`) — format the violation +
  legal-action set + context into the corrective tool-result the agent receives; track the
  per-agent correction count and trip the honest-failure path.

**Scope.**
- **v1:** corrective error (diagnosis + legal-action set + context) + bounded → honest fail.
- **v2:** stronger nudge (re-inject the agent's current prompt step; monitor proactively announces
  "you should be at step 4").

**Demo target.** Run it against the custom `hotfix` protocol
(`tracefix.pipeline/custom_demo/hotfix`) — force an out-of-order call and show the agent get
guided back.

---

## Cross-cutting: the `tools.json` contract (the real generalization) [F3 + F6]

`tools.json` is the spine through **prompt generation** (domain tool calls + parameter values)
**and** the **runtime** (which domain tools exist), yet it is currently defined as a benchmark
artifact (`benchmark/descriptions/{id}/tools.json`), and `/tla-prompt-gen` lists it as a
**required** input. So a custom task that verifies still stalls at prompt generation.

Generalization (not part of the two accepted designs, but the highest-leverage follow-up):
1. Make `tools.json` a **first-class, user-providable contract** with a documented schema.
2. A way to **author or synthesize** it for custom tasks (extract candidate tools from the prose
   during 1.1 and echo for confirmation).
3. A **default mapping to SDK builtins** (Read/Write/Edit/Bash) when no domain tools are declared.

---

## Evidence base — custom-task friction (from the hotfix run)

| ID | Friction | Severity | Nature |
|---|---|---|---|
| F0 | CLI only on PATH inside the venv | low | documented |
| F1 | No on-ramp (manual `mkdir` + write `description.md`; no `init`/template) | med | UX |
| F2 | No naming authority (IDs invented from prose; benchmark has `metadata.json`) | med | soft coupling |
| F3 | No `tools.json` → fidelity checks #10/#13 silently no-op; tool vocabulary unvalidated | med | soft coupling |
| F5 | Implicit `*_done:` terminal convention — unenforced by scaffold, unstated as a rule, unchecked; ending on a domain action yields asymmetric `states.json` (1 terminal vs 3) | med-high | benchmark-shaped |
| F6 | `/tla-prompt-gen` hard-requires `tools.json` sourced from the benchmark path | high | the real hard coupling |

Headline: the **verify** skill is general (custom task verified first try). The coupling is
downstream (F6) + a couple of unwritten conventions (F2/F3/F5).

---

## Roadmap (independent workstreams)

| # | Workstream | Decision | Side | First step |
|---|---|---|---|---|
| A | Coordination plan / draft layer | 2.1 ✓ | pipeline + skill | SKILL.md Phase 1.5 + `plan.md` convention (v1) |
| B | Monitoring correction | 4.3 ✓ | runtime | `StateTracker.legal_actions` + corrective dispatch (v1) |
| C | `tools.json` contract generalization | (F6 follow-up) | pipeline + runtime | document schema; user-providable; SDK-builtin default |
| D | On-ramp + conventions | (F1/F2/F5) | skill + CLI | `init` scaffold; add `*_done:` to scaffold/rules |
| — | Domain-info data plane | 4.4 | runtime | **parked** until distributed Phase 2 |

Suggested order: **B** (local, immediate, demoable on the hotfix protocol) → **A** (removes the
biggest design-time failure mode) → **C** (unblocks custom tasks end-to-end) → **D** (polish).

Open sub-decisions deferred: A and B each have a v1/v2 split (above); pick v1 first for both.
