"""Workspace layout: each task workspace is categorized into subfolders.

    workspace/<task>/
      description.md, tools.json   ← task inputs
      spec/      ir.json, Protocol*.tla, *.cfg, states.json, summary.json,
                 tlc_output.log, tlc_error.md, history/
      prompts/   runtime_b/
      output/    agent runtime artifacts (what the agents actually produce)

Resolution is **backward-compatible**: if a workspace has no ``spec/`` subdir,
spec files are read from the workspace root (the older flat layout), so existing
workspaces and the committed examples keep working without migration.
"""

from __future__ import annotations

import re
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


def _safe_name(name: str) -> str:
    """A filesystem-safe directory name derived from an agent id."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name).strip("_") or "agent"
    return f"{safe}_" if safe == "shared" else safe  # never collide with shared/


def shared_workdir(run_output: Path) -> Path:
    """The SHARED area under a run's ``output/`` — every agent's working directory.

    Files that another agent must read, or that the verified protocol coordinates
    (its lock-protected resources), live here. A bare filename an agent writes lands
    here, so the existing message → file → message handoffs keep working.
    """
    d = run_output / "shared"
    d.mkdir(parents=True, exist_ok=True)
    return d


def agent_workdir(run_output: Path, agent_id: str) -> Path:
    """A PRIVATE per-agent directory under a run's ``output/``.

    For files only that agent uses — scratch, its own test files, intermediate
    work — so they neither collide with peers nor clutter the shared area. NOT
    governed by the verified protocol (which only covers IR-declared resources).
    """
    d = run_output / _safe_name(agent_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_run_stamp() -> str:
    """A sortable timestamp label for one run, e.g. ``20260603-001234``."""
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d-%H%M%S")


#: Base-workspace entries that are per-run OUTPUT (not pipeline source) and so are
#: NOT carried into a fresh snapshot.
_SNAPSHOT_SKIP = {"output"}


def snapshot_run_workspace(base: Path, stamp: str) -> Path:
    """Create ``<base>-<stamp>/`` next to ``base`` as one run's self-contained
    workspace snapshot, and return it.

    Each run materializes the FULL pipeline products under a timestamped sibling
    of the base workspace: the inputs (``description.md`` / ``tools.json``), the
    verified ``spec/`` (ir.json, Protocol*.tla, states.json, …) and ``prompts/``
    are copied in, plus a fresh ``output/`` for this run's artifacts. The base
    workspace stays the canonical template/source; runs never overwrite each
    other, and every folder records exactly which spec produced which output. A
    best-effort ``<base>-latest`` symlink points at the newest run.

    The base's own ``output/`` and dotfiles are skipped — and because snapshots
    are SIBLINGS of the base, copying can never recurse into a prior snapshot.
    """
    import shutil
    dest = base.parent / f"{base.name}-{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    for item in sorted(base.iterdir()):
        if item.name in _SNAPSHOT_SKIP or item.name.startswith("."):
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
    (dest / "output").mkdir(exist_ok=True)
    link = base.parent / f"{base.name}-latest"
    try:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(dest.name)  # relative target → portable if workspace/ moves
    except OSError:
        pass  # symlinks may be unsupported; the timestamped dir is the source of truth
    return dest
