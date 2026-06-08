# 2PC minimal — a bundled, verified example

A complete, **already-verified** Two-Phase Commit protocol you can use to (a) confirm
your toolchain works and (b) see what every design+verify artifact looks like — with
**no LLM and no API keys**.

A coordinator asks two workers to `prepare`; each worker either reserves its resource
(a `Lock`) and votes `yes`, or votes `no`. The coordinator `commit`s only if both vote
yes, otherwise it `abort`s. TLC proves there is no deadlock, no double-locking, every
lock is released, every channel drained, and all agents terminate.

## What's here

| File | Role | Produced by |
|---|---|---|
| `ir.json` | coordination topology (3 agents, 2 locks, 4 channels) | hand-written input |
| `Protocol.tla` | PlusCal protocol (scaffold + filled process bodies) | `scaffold` + manual edit |
| `Protocol.cfg` | TLC config (CONSTANTS, INVARIANTs, ChannelBound) | `scaffold` |
| `Protocol_translated.tla` | TLA+ after `pcal.trans` | `verify` |
| `states.json` | per-agent state machine (runtime ground truth) | `extract-states` |

## Run it

From the repo root, with the toolchain installed (`bash scripts/download_tla2tools.sh`
+ Java 17 — check with `tla-verify-pluscal doctor`):

```bash
tla-verify-pluscal validate examples/2pc_minimal/ir.json
tla-verify-pluscal verify   examples/2pc_minimal          # → PASS (≈145 distinct states, <1s)
tla-verify-pluscal extract-states examples/2pc_minimal    # → states.json
```

`verify` re-creates `Protocol_translated.tla` and a `tlc_output.log`; both are
deterministic for this spec. `tla-verify-pluscal doctor` runs exactly this verification
as its end-to-end smoke test.

## Try breaking it (see the repair feedback)

Make worker A acquire its lock but never release it on the abort path — delete the
`a_release_abort: release_lock(res_A);` line — and re-run `verify`. TLC will report a
`NoOrphanLocks` safety violation with a counterexample trace showing exactly how the
lock is left held at `Done`. That trace is what drives the automated repair loop.
