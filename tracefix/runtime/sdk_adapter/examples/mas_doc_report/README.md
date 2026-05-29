# Example: collaborative report writing (real end-to-end MAS task)

A **real, non-dummy** end-to-end demo: three agents **concurrently write ONE
shared `report.md`**, with a TLA+-verified lock preventing lost updates. Unlike
the benchmark tasks (whose domain tools are dummy sims that return fake data),
here the agents use the SDK's **real Read/Write/Edit tools** and produce an
actual document.

## What it demonstrates

**control/data plane separation, in practice:**
- **control plane** (tracefix-verified): the `REPORT` lock + `submit` flag channels
- **data plane** (SDK real tools): the actual `report.md` content

**Lock value, demonstrated for real:** `WRITER_LOCKS` and `WRITER_CHANNELS` both
do a read-modify-write on the *same* `report.md`. The `REPORT` lock serializes
them, so neither overwrites the other (no lost update). In the committed sample
run, `WRITER_LOCKS` **blocked ~18s** waiting for the lock — real contention, not
simulated. Both sections survive in the final document → the lock worked.

## Which tracefix stages this exercises

This demo drives tracefix's **deterministic verification core + runtime
coordination layer** end-to-end. The **LLM-automation stages were done by hand**:

| tracefix stage | this demo |
|---|---|
| IR validation (`validate`) | ✅ exercised |
| scaffold IR→PlusCal (`scaffold`) | ✅ exercised |
| PlusCal→TLA+ compile + TLC model-check (`verify`, **PASS**) | ✅ exercised |
| state extraction (`extract-states`) | ✅ exercised |
| runtime coordination: Monitor + StateTracker + stores | ✅ exercised (via SDK adapter) |
| IR design / PlusCal authoring / prompt generation | ✍️ **hand-written** (not the LLM pipeline) |
| TLC repair loop | — not triggered (PlusCal passed first try) |
| enforcement (arch A) / baselines | — not used |

`ir.json` + `Protocol.tla` + the per-agent prompts here were written by hand,
then TLC-verified. The LLM pipeline's auto-design is exercised separately via
`python -m tracefix.pipeline`.

## Topology

```
WRITER_LOCKS    ─┐  writes "Locks & Mutual Exclusion"
WRITER_CHANNELS ─┤  writes "Channels & Control/Data Plane"   ──submit──► EDITOR
                 └─ both contend for the REPORT lock over report.md     adds intro/conclusion, integrates
```

## Run it — sub-agents on OpenAI (via LiteLLM proxy)

Prereqs: the Claude CLI, `pip install claude-agent-sdk 'litellm[proxy]'`, and
`OPENAI_API_KEY` in the repo-root `.env`.

```bash
# 1. start the proxy (translates Anthropic <-> OpenAI under the hood)
set -a && . ./.env && set +a
litellm --config tracefix/runtime/sdk_adapter/examples/mas_doc_report/litellm_config.yaml --port 4000 &

# 2. run the 3 agents on gpt-5-mini, routed through the proxy
ANTHROPIC_BASE_URL=http://localhost:4000 ANTHROPIC_AUTH_TOKEN=sk-tracefix-local \
python -m tracefix.runtime.sdk_adapter run --task mas_doc \
  --workspace tracefix/runtime/sdk_adapter/examples/mas_doc_report \
  --model gpt-5-mini --builtins Read,Write,Edit --verbose
```

The two env vars only affect this command's sub-process (and the `claude` CLI it
spawns) — they do **not** change your own Claude Code or any global config.

To run sub-agents on **Claude** instead (no proxy needed): drop the
`ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` env vars and the `--model` flag.

## Output

The agents write to `/tmp/mas_doc_demo/output/report.md` (the path hard-coded in
the prompts — edit the prompts to change it). A real sample run's output is
committed here at [`output/report.sample.md`](output/report.sample.md).
