# Runtime A Prompt Generation (Framework-Driven)

In Runtime A, the coordination framework (mediator) handles **all** coordination automatically — locks, messages, and scheduling. The agent is called by the framework at the right time and only needs to:
1. Perform domain work (call domain tools)
2. Make decisions at decision points (accept/reject, pass/fail, etc.)

The agent does NOT know about lock IDs, channel IDs, or coordination tools. It only sees its domain and a `respond_decision` tool.

## Prompt Structure (3 Layers)

```
Layer 1: Context          — Who you are, system overview, your role in the team
Layer 2: Decision Points  — What decisions you'll be asked to make, with domain context
Layer 3: Workflow          — Step-by-step with domain tools only
```

**Note on tools**: Do NOT include a `## Tools` section in the prompt. The runtime provides all tool schemas (domain + `respond_decision`) to the LLM via function calling. The prompt only needs to reference tool names in the workflow steps.

## Layer 1: Context

Provide three things — same as Runtime B but **without protocol topology diagram** (agent doesn't know about channels):

1. **Role**: One sentence describing the agent's function
2. **System overview**: Who else is in the system, described in domain terms (not coordination terms)
3. **Framework note**: One sentence explaining that the framework handles coordination

Example:
```markdown
## 1. Context

You are **researcherA** in a collaborative paper-writing team.

**Your role**: Research and write a section on subtopic A, submit for
fact-checking and editorial review, revise if needed.

**System overview**: You work alongside researcherB (subtopic B),
a factchecker (verifies your claims), and an editor (ensures
cross-section consistency between your work and researcherB's).

The coordination framework manages all scheduling, resource access,
and message delivery automatically. Focus on doing your domain work well.
```

**Key difference from Runtime B**: No protocol topology diagram, no mention of channels/locks. Describe collaborators in domain terms ("factchecker verifies your claims") not coordination terms ("factchecker receives on fc_to_resA").

## Layer 2: Decision Points

List every decision the agent will be asked to make during the protocol. For each decision, provide:

1. **When it happens**: What triggers this decision (who sends the result)
2. **What the options mean**: Domain-level explanation of each choice
3. **Judgment guidance**: What should the agent consider when deciding (for `either/or` nondeterministic choices where the agent exercises judgment)

### Identifying Decision Points from PlusCal

| PlusCal pattern | Decision type | Example |
|---|---|---|
| `receive(ch, msg); if (msg = "X") { ... } else { ... }` | **Reactive**: framework delivers a message, agent responds based on label | Fact check result: pass/flag |
| `either { send(ch, "approve") } or { send(ch, "reject") }` | **Judgmental**: agent decides which branch based on domain knowledge | Reviewer approves or rejects submission |
| `either { ... } or { ... }` (pure nondeterminism, no agent judgment) | **Skip** — the framework handles this, not the agent | |

### Decision Point Template

```markdown
## 2. Decision Points

During your workflow, the framework will present you with decisions.

### Fact Check Result
**When**: After the factchecker reviews your section.
**Options**:
- **"pass"** — Your claims and citations are verified. Call `respond_decision("continue")`.
- **"flag"** — Some claims could not be verified. Call `respond_decision("revise")` and go back to Step 1 to strengthen your sources.

### Editorial Review Result
**When**: After the editor compares your section with researcherB's for consistency.
**Options**:
- **"accept"** — Your section is approved as-is. Call `respond_decision("done")`.
- **"revise"** — There are contradictions or redundancies with the other section. Call `respond_decision("revise")` and go to Step 4 to fix them.
```

**For judgmental decisions** (reviewer approve/reject), add guidance:
```markdown
### Review Decision
**When**: After you read the submitted code.
**Your judgment**: Evaluate the code quality, correctness, and adherence to standards.
**Options**:
- If the code meets standards: Call `respond_decision("approve")`
- If the code has issues: Call `respond_decision("reject")`
```

## Layer 3: Workflow

Step-by-step instructions with **domain tools only**. No coordination tool calls.

### PlusCal Translation Rules (Runtime A)

| PlusCal construct | Runtime A prompt |
|---|---|
| `acquire_lock(X)` / `release_lock(X)` | **Omit entirely** — the framework handles this |
| `send(ch, "label")` | **Omit** — the framework sends on your behalf |
| `receive(ch, msg)` | "You will receive [sender]'s response" (passive voice) |
| `if (msg = "X") { ... }` after receive | Reference the Decision Point from Layer 2 |
| `either/or` (agent judgment) | Reference the Decision Point from Layer 2 |
| `either/or` (pure nondeterminism) | **Omit** — framework handles |
| Domain tool calls | Keep as-is |
| `while(TRUE) { ... }` | "Repeat Steps N-M until done" |
| `goto label` | "Go to Step N" |
| Process end | "Your work is complete." |

### Label-to-Step Consolidation (Runtime A)

Runtime A consolidates more aggressively than Runtime B because coordination labels disappear. As with Runtime B, consolidation merges adjacent labels into one step but does NOT reorder — the step sequence must match PlusCal control flow:

| Pattern | Consolidation |
|---|---|
| **acquire + work + release** | Just the work: "Write your draft" (no acquire/release) |
| **receive + if/else dispatch** | "Respond to [sender]'s verdict" — reference Decision Point |
| **sequential sends** | **Omit entirely** |
| **release + immediate send** | **Omit** — the framework handles both |
| **label with only `skip`** | Terminal step: "Done" |

### Domain Tool Integration

Same as Runtime B, but without coordination calls wrapping them:

```markdown
### Step 1: Write Draft
- Call `research_topic(topic="subtopic A")` to gather sources
- Call `write_section(section_name="section A")` to write your draft
```

Not:
```markdown
### Step 1: Write Draft
- Call `acquire_lock("doc_lock")`          ← OMIT
- Call `research_topic(topic="subtopic A")`
- Call `write_section(section_name="section A")`
- Call `release_lock("doc_lock")`          ← OMIT
```

## Template

Use this structure for each `prompts/runtime_a/{agent_id}.md`:

~~~markdown
# {Agent ID} — Agent Prompt (Runtime A)

## 1. Context

You are **{agent_id}** in a multi-agent system.

**Your role**: {one-sentence role description}

**System overview**: {who else is in the system, described in domain terms}

The coordination framework manages all scheduling, resource access, and message delivery automatically. Focus on doing your domain work well.

## 2. Decision Points

During your workflow, the framework will present you with decisions.

### {Decision Name}
**When**: {what triggers this decision}
**Options**:
- **"{label_a}"** — {domain explanation}. Call `respond_decision("{choice_a}")`.
- **"{label_b}"** — {domain explanation}. Call `respond_decision("{choice_b}")`.

...

## 3. Workflow

### Step 1: {Step Name}
{description with domain tool calls only}

### Step 2: {Step Name}
You will receive {sender}'s verdict.
→ See **Decision Point: {name}** above.

...

### Step N: Done
Your work is complete.
~~~

## Example: researcherA in task 3M

### Generated Prompt

~~~markdown
# researcherA — Agent Prompt (Runtime A)

## 1. Context

You are **researcherA** in a collaborative paper-writing team.

**Your role**: Research and write a section on subtopic A, submit for fact-checking and editorial review, revise if needed.

**System overview**: You work alongside researcherB (subtopic B), a factchecker (verifies your citations and claims), and an editor (ensures cross-section consistency between your work and researcherB's).

The coordination framework manages all scheduling, resource access, and message delivery automatically. Focus on doing your domain work well.

## 2. Decision Points

During your workflow, the framework will present you with decisions.

### Fact Check Result
**When**: After the factchecker reviews your section's citations and claims.
**Options**:
- **"pass"** — All claims verified. Call `respond_decision("continue")`.
- **"flag"** — Some claims could not be verified. Call `respond_decision("revise")` and go back to Step 1 to strengthen your sources.

### Editorial Review Result
**When**: After the editor compares your section with researcherB's for consistency.
**Options**:
- **"accept"** — Your section is approved as-is. Call `respond_decision("done")`.
- **"revise"** — There are contradictions or redundancies with the other section. Call `respond_decision("revise")` and go to Step 4.

## 3. Workflow

### Step 1: Write Draft
- Call `research_topic(topic="subtopic A")` to gather sources
- Call `write_section(section_name="section A")` to write your draft

### Step 2: Update References
- Call `update_references(section_name="section A")`

### Step 3: Respond to Fact Check
You will receive the factchecker's verdict.
→ See **Decision Point: Fact Check Result** above.

### Step 4: Respond to Editorial Review
You will receive the editor's decision.
→ See **Decision Point: Editorial Review Result** above.

### Step 5: Revise for Consistency
- Call `revise_section(section_name="section A", feedback="editor: cross-section inconsistency")`

### Step 6: Done
Your work is complete.
~~~
