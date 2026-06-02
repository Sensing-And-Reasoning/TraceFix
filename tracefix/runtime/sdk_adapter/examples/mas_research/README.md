# Example: research-brief MAS (6 agents, real end-to-end)

A **real, non-dummy** end-to-end demo: six agents collaboratively research the **future
directions of verifying LLM multi-agent systems** and produce one reviewed document. Unlike the
benchmark tasks (dummy sim tools), the agents use the SDK's **real Read/Write** tools and emit an
actual markdown brief. It is a richer, 6-agent counterpart to `mas_doc_report`.

## Topology

```
RESEARCHER_FM   ─┐  formal-methods direction
RESEARCHER_RT   ─┤  runtime-monitoring direction   ── all write research.md under the DOC lock
RESEARCHER_EVAL ─┘  evaluation direction                (mutual exclusion: no lost updates)
                     │ each sends "ready" ×2 (fan-in)
                     ├──research_to_plotter──► PLOTTER   adds a taxonomy figure (under DOC lock)
                     └──research_to_checker──► CHECKER   verifies claims → data_check.md (no lock)
                                                  │            │
                                          figures │            │ verified
                                                  └──► APPROVER ◄──┘   reads all → ACCEPTANCE.md
```

## What it demonstrates

- **Control/data-plane split.** Control plane (tracefix-verified): the `DOC` lock + the four
  message channels. Data plane (SDK real tools): the actual `research.md` content.
- **Mutual exclusion, for real.** The three researchers contend for `DOC` and serialize their
  writes to the *same* `research.md`. In the committed sample run the acquisition order was
  `EVAL → RT → FM` (FM's `acquire_lock` timed out twice waiting) — real contention, not
  simulated. All three sections + the figure survive in the final document → no lost updates.
- **Multi-sender fan-in channels.** `research_to_plotter` / `research_to_checker` each have
  three senders; PLOTTER/CHECKER receive three times in **any arrival order** — so the monitor
  imposes no artificial receive-ordering on independent producers.
- **Honest monitoring.** Every coordination op is validated against `spec/states.json`; the
  sample run finished with **0 violations**.

## Which tracefix stages this exercises

| tracefix stage | this demo |
|---|---|
| IR validation (`validate`) | ✅ |
| scaffold IR→PlusCal (`scaffold`) | ✅ |
| PlusCal→TLA+ compile + TLC model-check (`verify`, **PASS**, 10007 states / 0.6s) | ✅ |
| state extraction (`extract-states` → 39 states, 6 terminal) | ✅ |
| runtime coordination: Monitor + StateTracker + stores (SDK adapter) | ✅ |
| IR design / PlusCal authoring / prompt generation | ✍️ hand-written, then TLC-verified |

`ir.json` + `Protocol.tla` + the per-agent prompts were authored by hand and TLC-verified; the
LLM auto-design pipeline is exercised separately via `python -m tracefix.pipeline`.

## Layout (spec/ + prompts/ convention)

```
spec/       ir.json · Protocol*.tla · Protocol.cfg · states.json · tlc_output.log
prompts/    runtime_b/{RESEARCHER_FM,RESEARCHER_RT,RESEARCHER_EVAL,PLOTTER,CHECKER,APPROVER}.md
sample_run/ research.md · data_check.md · ACCEPTANCE.md   (a committed gpt-5-mini sample run)
description.md · litellm_config.yaml
```

## Run it — sub-agents on OpenAI (via LiteLLM proxy)

Prereqs: the Claude CLI, `pip install claude-agent-sdk 'litellm[proxy]'`, and `OPENAI_API_KEY`
in the repo-root `.env`.

```bash
# 1. start the proxy (translates Anthropic <-> OpenAI under the hood)
set -a && . ./.env && set +a
litellm --config tracefix/runtime/sdk_adapter/examples/mas_research/litellm_config.yaml --port 4000 &

# 2. run the 6 agents on gpt-5-mini, routed through the proxy, with live visualization
ANTHROPIC_BASE_URL=http://127.0.0.1:4000 ANTHROPIC_AUTH_TOKEN=sk-tracefix-local \
python -m tracefix.runtime.sdk_adapter run --task mas_research \
  --workspace tracefix/runtime/sdk_adapter/examples/mas_research \
  --model gpt-5-mini --builtins Read,Write,Edit --timeout 600 --live --verbose
```

The env vars only affect this command's sub-process (and the `claude` CLI it spawns) — they do
**not** change your own Claude Code or any global config. To run sub-agents on **Claude** instead
(no proxy): drop the two env vars and the `--model` flag. `--timeout 600` gives the serialized
critical sections room; a slower model may need more.

## Output

Running writes fresh `research.md` / `data_check.md` / `ACCEPTANCE.md` into `output/` (gitignored).
A committed sample run is in [`sample_run/`](sample_run/) — `SUCCESS in 377.7s`, 6/6 completed,
monitor clean, verdict **ACCEPTED WITH NITS**. (The sample was produced by gpt-5-mini and has a
couple of cosmetic unicode glitches in the prose — a model artifact, not a tracefix issue.)
