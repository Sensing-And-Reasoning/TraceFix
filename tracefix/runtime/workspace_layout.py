"""Workspace layout: each task workspace is categorized into subfolders.

    workspace/<task>/
      description.md, tools.json   ← task inputs
      spec/      ir.json, Protocol*.tla, *.cfg, states.json, summary.json,
                 tlc_output.log, tlc_error.md, history/
      prompts/   runtime_a/, runtime_b/
      output/    agent runtime artifacts (what the agents actually produce)

Resolution is **backward-compatible**: if a workspace has no ``spec/`` subdir,
spec files are read from the workspace root (the older flat layout), so existing
workspaces and the committed examples keep working without migration.
"""

from __future__ import annotations

from pathlib import Path


def spec_dir(workspace: Path) -> Path:
    """The ``spec/`` subdir if present, else the workspace root (flat fallback)."""
    d = workspace / "spec"
    return d if d.is_dir() else workspace


def spec_path(workspace: Path, name: str) -> Path:
    """Resolve a spec artifact (e.g. ``ir.json``, ``states.json``)."""
    return spec_dir(workspace) / name


def output_dir(workspace: Path) -> Path:
    """Directory for agent runtime artifacts; created if missing.

    Used as the SDK agents' ``cwd`` so files they write land here instead of
    polluting the workspace root (or the launch directory).
    """
    d = workspace / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d
