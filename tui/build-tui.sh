#!/usr/bin/env bash
#
# Build the TraceFix TUI — a thin fork of opencode (MIT) that is TraceFix's
# native, interactive protocol-design front end. This script clones the fork,
# installs its toolchain, and compiles the single-file binary.
#
# The TUI is OPTIONAL: the headless `tracefix design` and the Claude Code
# `/tla-verify-pluscal` skill give the full design+verify flow without it. Build
# the TUI only if you want the native interactive `/design` experience.
#
# Prerequisites: git, and bun >= 1.3.14 (https://bun.sh). The fork builds a
# ~92 MB native binary; the build needs ~5 GB of scratch for node_modules.
#
# Usage:
#   TRACEFIX_TUI_REPO=<url> ./tui/build-tui.sh    # clone + build
#   ./tui/build-tui.sh                            # if REPO is set below or in env
#
set -euo pipefail

# --- the fork repo (override with env) --------------------------------------
# Set this to your TraceFix TUI fork once it is pushed. The `tracefix` branch
# carries the patches listed in the fork's PATCHES.md on top of opencode v1.17.4.
REPO="${TRACEFIX_TUI_REPO:-https://github.com/xsrxdc/TraceFix-TUI.git}"
BRANCH="${TRACEFIX_TUI_BRANCH:-tracefix}"
DEST="${TRACEFIX_TUI_DIR:-$HOME/tracefix-tui-src}"

if [[ "$REPO" == *YOUR_USERNAME* ]]; then
  echo "ERROR: set TRACEFIX_TUI_REPO (or edit REPO in this script) to your fork URL." >&2
  exit 1
fi

command -v bun >/dev/null 2>&1 || { echo "ERROR: bun not found — install from https://bun.sh (need >= 1.3.14)." >&2; exit 1; }
echo "bun $(bun --version)"

# --- clone or update --------------------------------------------------------
if [ -d "$DEST/.git" ]; then
  echo "Updating existing checkout: $DEST"
  git -C "$DEST" fetch origin "$BRANCH"
  git -C "$DEST" checkout "$BRANCH"
  git -C "$DEST" pull --ff-only origin "$BRANCH"
else
  echo "Cloning $REPO ($BRANCH) -> $DEST"
  git clone --branch "$BRANCH" "$REPO" "$DEST"
fi

# --- install + build --------------------------------------------------------
cd "$DEST"
bun install
bun run packages/opencode/script/build.ts --single --skip-embed-web-ui

# --- report the binary ------------------------------------------------------
BIN="$(ls "$DEST"/packages/opencode/dist/tracefix-tui-*/bin/opencode 2>/dev/null | head -1 || true)"
if [ -z "$BIN" ]; then
  echo "Build finished but no binary found under packages/opencode/dist/. Check the log above." >&2
  exit 1
fi
echo
echo "Built TraceFix TUI: $BIN"
echo "Smoke test:"; "$BIN" --version || true
echo
echo "Next:"
echo "  1. Put it on PATH, e.g.:  ln -sf \"$BIN\" /usr/local/bin/tracefix-tui"
echo "  2. In a project where this repo is installed (pip install -e .), launch: tracefix-tui"
echo "     The designer agent resolves 'tla-verify-pluscal' + the design guide from that install."
