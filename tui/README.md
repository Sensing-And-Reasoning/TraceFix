# TraceFix TUI

TraceFix's native, interactive protocol-design front end — a **thin fork of
[opencode](https://github.com/sst/opencode)** (MIT) whose only visible agent is
the TraceFix `designer`. You describe a multi-agent coordination requirement in
plain language; the designer asks clarifying questions, pauses for your approval
of the coordination plan, then derives + TLC-verifies the protocol and generates
per-agent runtime prompts — all inside the terminal UI.

## Why it is a separate repository

The TUI is a **fork tracked separately on purpose**, not part of this repo's
source tree. Its `origin` stays pointed at upstream opencode so new releases can
be pulled and the TraceFix patches re-applied by cherry-pick (the patch set is
the fork's `PATCHES.md`). Vendoring the ~5 GB monorepo here would bloat this repo
and sever that upstream-sync path. **This `tui/` directory is the recipe — how to
get and build the fork — not its source.**

The two pieces are one product but two repos:

| Repo | Role |
|------|------|
| **this repo** (`tracefix-public`) | the Python verification platform: the `tla-verify-pluscal` CLI, the design knowledge (`.claude/skills/`), benchmarks, runtimes |
| **the TUI fork** (`tracefix` branch) | the interactive front end you type in; its `designer` agent calls `tla-verify-pluscal guide` + the CLI from the install above |

## This is the primary way to use TraceFix

The TUI is the intended, first-choice entry point: build it once and `/design`
interactively. If you'd rather not run a separate binary and already work inside
your own agent harness, the **second choice** is the `/tla-verify-pluscal` skill
in Claude Code — the same workflow and review gates, using this repo's
`.claude/skills/`.

(There is also a non-interactive `tracefix design "<requirement>"` for
automation/CI/benchmarking — same workflow, no review gate. It is not the
recommended way to design interactively; use the TUI or the skill for that.)

## Build

```bash
# 1. Install this repo so the toolchain + design guide are available:
pip install -e .                  # from the repo root
bash scripts/download_tla2tools.sh
tla-verify-pluscal doctor         # confirm Java 17 + jar + tree-sitter

# 2. Build the TUI binary (needs bun >= 1.3.14 and ~5 GB scratch):
TRACEFIX_TUI_REPO=<your fork url> ./tui/build-tui.sh
```

The script clones the fork's `tracefix` branch, runs `bun install`, compiles the
single-file binary (`--single --skip-embed-web-ui`), and prints its path plus a
PATH/symlink hint. Launch `tracefix-tui` in any project where this repo is
installed; the designer resolves `tla-verify-pluscal` and the design guide from
that install regardless of the launch directory.

## Keeping the fork in sync with upstream

See `PATCHES.md` in the fork repo: it lists every TraceFix patch in cherry-pick
order and documents the release-tracking procedure (recreate the branch at the
new upstream tag, cherry-pick the manifest, rebuild).
