# Example: ping-pong (minimal runnable workspace)

A hand-written two-agent workspace — no pipeline run required — for smoke-testing
the SDK adapter end-to-end. The public repo ships no pipeline-generated
workspace, so this is the fastest way to see SDK-driven agents coordinate.

## Protocol

```
PINGER ──ping_ch (label "ping")──► PONGER
   ▲                                  │
   └──────── pong_ch (label "pong") ──┘
```

`PINGER` writes a file, sends `ping`, waits for `pong`, then finishes. `PONGER`
waits for `ping`, writes a file, replies `pong`, then finishes. Both file writes
go to `/tmp/tracefix_pingpong/` so running this does not touch the repo.

There is intentionally no `states.json` — with no state tracker, `signal_done`
is ungated, which keeps the example minimal. (Add a `states.json` to exercise
`StateTracker` early-termination gating.)

## Run

Requires `pip install claude-agent-sdk` and an authenticated Claude CLI (see
the adapter README).

```bash
python -m tracefix.runtime.sdk_adapter run \
    --task ping_pong \
    --workspace tracefix/runtime/sdk_adapter/examples/ping_pong \
    --builtins Read,Write --verbose
```

(`--task ping_pong` has no benchmark sim, so you'll see a harmless
"no benchmark tools" notice — the agents run with coordination + built-in tools.)

## Expected result

```
=== SDK Adapter Result ===
SUCCESS in ~20s
  PINGER: 3 tool calls, completed
  PONGER: 3 tool calls, completed
```

and two files under `/tmp/tracefix_pingpong/`:
`pinger_note.txt` → "PINGER did real work", `ponger_note.txt` → "PONGER received the ping".
