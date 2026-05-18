# Phase 5: Generate Per-Agent Prompts

After extracting states (Phase 4), generate per-agent workflow prompts in **two variants** — one for each runtime architecture. Generate them **sequentially**: Runtime B first (more complex), then Runtime A (simpler).

**Output structure:**
```
prompts/
  runtime_b/{agent_id}.md   — Agent-driven: agent calls coordination tools explicitly
  runtime_a/{agent_id}.md   — Framework-driven: agent does domain work + decisions only
```

## Step 1 — Gather Inputs

1. Re-read `summary.json` — note `total_repairs` and repair types. If repairs were needed (e.g., deadlock fixes), prioritize the corresponding Critical Rules when generating Runtime B prompts.
2. Re-read `Protocol.tla` (the verified PlusCal source)
3. Re-read `ir.json` (topology: agents, resources, channels with labels)
4. Recall the task description from the user's original input
5. Re-read `tools.json` from the task directory (already read in Phase 1 Step 0). Filter tools by `agent_ids` when generating each agent's prompt. If no `tools.json` was provided, skip domain tool integration and note: "No domain tool schema available."
6. Read `states.json` (generated in Phase 4). This is the **ground truth** for all states, transitions, and coordination operations per agent. It includes `tool_hint` annotations on multi-action states (`receive_any` or `poll_channels`).

## Step 2 — Generate Runtime B Prompts (do this FIRST)

Runtime B prompts are the most detailed — each agent gets **explicit, step-by-step instructions** covering every coordination call, every decision point, and every domain tool call with concrete parameters. The agent must know exactly what to do at each step and in every situation (receive "pass" → do X, receive "flag" → do Y).

Follow [prompt-gen-runtime-b.md](prompt-gen-runtime-b.md) for the complete template, 3-layer structure, translation rules, and example.

For **each agent**, complete sub-steps 2a through 2d in order:

### Step 2a — Per-Agent State Inventory (MANDATORY)

Read `states.json` and for each agent list:
- All state IDs belonging to this agent + initial state
- Per-state: action count, coordination ops (`acquire`/`release`/`send`/`receive` + resource/channel IDs), `next_state`
- `tool_hint` value for multi-action states (if present)
- Terminal states (empty `actions` array or `next_state: "__done__"`)

### Step 2b — Label-to-Step Mapping Table (MANDATORY)

Before writing any prose, build a mapping table using `states.json` as ground truth:

```
| PlusCal States (from states.json) | Prompt Step | Consolidation Rule | Coordination Calls |
|---|---|---|---|
| `int_wait` (tool_hint: receive_any) + `int_check` | Step 1: Collect Stable Signals | all-recv either/or → receive_any + loop | receive_any([ch_bA_int, ch_bB_int, ch_bC_int]) |
| `int_link` | Step 2: Link Modules | standalone work | (domain only) |
| `int_notify` + done | Step 3: Notify & Done | send + done | send_message("ch_int_tr", "all_done"), signal_done() |
```

Rules:
- Every state from Step 2a MUST appear in exactly one row
- `Coordination Calls` column lists exact tool calls with exact IDs from `states.json`
- Use `tool_hint` to determine `receive_any` vs `poll_channels` vs `receive_message`

### Step 2c — Generate Prompt Following the Mapping Table

Write each step strictly from the table. Coordination calls must match the "Coordination Calls" column exactly. Key requirements:
- Domain tool calls must include concrete parameter values (consult `tools.json` for valid values and the task description for semantic mapping)
- When `either/or` branches receive from different channels, map each channel source to the appropriate domain tool parameters — do NOT hardcode a single parameter value
- The final step must say `Call signal_done()`
- Do NOT include a `## Tools` section — the runtime injects tool schemas automatically

### Step 2d — Verify Prompt Against states.json (MANDATORY)

After each agent's prompt, run through this verification checklist:

| Check | How | Fail → |
|---|---|---|
| All states covered | Every state ID for this agent in `states.json` appears in mapping table | Add missing state |
| All branches covered | State with N actions → prompt has N branches | Add missing branch |
| Channel IDs exact | `send`/`receive` channel in `states.json` matches prompt tool arg | Fix ID |
| Lock IDs exact | `acquire`/`release` resource in `states.json` matches prompt tool arg | Fix ID |
| Labels exact | `send` label in `states.json` matches `send_message()` label arg | Fix label |
| Tool selection | `tool_hint: receive_any` → `receive_any`; `poll_channels` → `poll_channels` | Switch tool |
| Terminal | Last step has `signal_done()` | Add it |
| No phantom ops | No coord calls in prompt that aren't in `states.json` | Remove |

## Step 3 — Generate Runtime A Prompts

Runtime A prompts are simpler — no coordination tools, no protocol topology. The agent only sees domain work and decision points.

Follow [prompt-gen-runtime-a.md](prompt-gen-runtime-a.md) for the complete template, 3-layer structure, translation rules, and example.

Runtime A prompts can often be derived by simplifying the corresponding Runtime B prompt: strip all `acquire_lock`/`release_lock`/`send_message`/`receive_message` calls, replace `signal_done()` with "Your work is complete", and convert coordination decision points into `respond_decision()` calls.

**Note on work state labels:** PlusCal `skip` labels that exist solely as intermediate work states between acquire and release (see pluscal-guide.md "Work State Labels") should be consolidated with their adjacent acquire/release into one prose step in the prompt — they do NOT become separate prompt steps.

## Step 4 — Report Summary

List the generated files for both `prompts/runtime_b/` and `prompts/runtime_a/`, and confirm each agent's prompt covers all PlusCal labels and decision points.
