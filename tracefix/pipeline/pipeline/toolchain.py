"""Cross-platform resolution of the Java 17 + tla2tools.jar toolchain.

Centralizes how TraceFix finds the external verification toolchain so the CLI,
the PlusCal compiler, the TLC runner, and `tla-verify-pluscal doctor` all agree.

Java resolution priority (first hit wins):
  1. explicit argument (e.g. ``--java-path``)
  2. ``TLA_VERIFY_JAVA`` environment variable
  3. the Homebrew ``openjdk@17`` keg path, if it exists (keg-only on macOS, so it
     is preferred over a possibly-older ``java`` on PATH)
  4. ``$JAVA_HOME/bin/java``, if it exists
  5. ``java`` on ``PATH`` (this is what makes Linux/Windows work out of the box)
  6. the Homebrew path as a last-resort default, so error messages name a path

JAR resolution priority: explicit arg → ``TLA_VERIFY_JAR`` env → bundled
``<repo>/lib/tla2tools.jar``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

_HOMEBREW_JAVA = "/opt/homebrew/opt/openjdk@17/bin/java"


def _repo_root() -> Path:
    return next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())


def resolve_java(explicit: str | None = None) -> str:
    """Resolve a Java binary path (see module docstring for priority)."""
    if explicit:
        return explicit
    env = os.environ.get("TLA_VERIFY_JAVA")
    if env:
        return env
    if Path(_HOMEBREW_JAVA).exists():
        return _HOMEBREW_JAVA
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        cand = Path(java_home) / "bin" / "java"
        if cand.exists():
            return str(cand)
    on_path = shutil.which("java")
    if on_path:
        return on_path
    return _HOMEBREW_JAVA  # last resort: a concrete path for the error message


def resolve_jar(explicit: str | None = None) -> str:
    """Resolve the tla2tools.jar path (explicit → env → bundled lib/)."""
    if explicit:
        return explicit
    env = os.environ.get("TLA_VERIFY_JAR")
    if env:
        return env
    return str(_repo_root() / "lib" / "tla2tools.jar")


def java_major_version(java_path: str) -> str | None:
    """Return the Java major version (e.g. ``"17"``) or None if java can't run.

    Handles both the modern scheme (``17.0.x`` → ``"17"``) and the legacy
    ``1.x`` scheme (``1.8.0`` → ``"8"``).
    """
    try:
        proc = subprocess.run(
            [java_path, "-version"], capture_output=True, text=True, timeout=10
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    out = (proc.stderr or "") + (proc.stdout or "")
    m = re.search(r'version "(\d+)(?:\.(\d+))?', out)
    if not m:
        return None
    major, minor = m.group(1), m.group(2)
    if major == "1" and minor:  # legacy 1.8 → 8
        return minor
    return major


JAVA_MISSING_HINT = (
    "Install Java 17 (e.g. `brew install openjdk@17` or your distro's package), "
    "then set TLA_VERIFY_JAVA=/path/to/java or pass --java-path."
)
JAR_MISSING_HINT = (
    "Run `bash scripts/download_tla2tools.sh` to fetch tla2tools.jar v1.8.0, "
    "or set TLA_VERIFY_JAR=/path/to/tla2tools.jar or pass --jar-path."
)
