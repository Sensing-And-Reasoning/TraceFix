"""Tests for cross-platform Java/jar toolchain resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from tracefix.pipeline.pipeline import toolchain


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("TLA_VERIFY_JAVA", raising=False)
    monkeypatch.delenv("TLA_VERIFY_JAR", raising=False)
    monkeypatch.delenv("JAVA_HOME", raising=False)


def test_resolve_java_explicit_wins(monkeypatch):
    monkeypatch.setenv("TLA_VERIFY_JAVA", "/env/java")
    assert toolchain.resolve_java("/explicit/java") == "/explicit/java"


def test_resolve_java_env_over_default(monkeypatch):
    monkeypatch.setenv("TLA_VERIFY_JAVA", "/env/java")
    assert toolchain.resolve_java() == "/env/java"


def test_resolve_java_falls_back_to_path(monkeypatch):
    # Homebrew keg absent, no JAVA_HOME → should use `java` on PATH.
    monkeypatch.setattr(toolchain.Path, "exists", lambda self: False)
    monkeypatch.setattr(toolchain.shutil, "which", lambda name: "/usr/bin/java")
    assert toolchain.resolve_java() == "/usr/bin/java"


def test_resolve_java_homebrew_preferred_when_present(monkeypatch):
    # Homebrew keg present → preferred over a (possibly older) java on PATH.
    monkeypatch.setattr(toolchain.Path, "exists", lambda self: True)
    monkeypatch.setattr(toolchain.shutil, "which", lambda name: "/usr/bin/java")
    assert toolchain.resolve_java() == toolchain._HOMEBREW_JAVA


def test_resolve_java_java_home(monkeypatch, tmp_path):
    java = tmp_path / "bin" / "java"
    java.parent.mkdir(parents=True)
    java.write_text("")
    monkeypatch.setattr(toolchain.Path, "exists",
                        lambda self: str(self) == str(java))
    monkeypatch.setenv("JAVA_HOME", str(tmp_path))
    monkeypatch.setattr(toolchain.shutil, "which", lambda name: None)
    assert toolchain.resolve_java() == str(java)


def test_resolve_jar_explicit_and_env(monkeypatch):
    assert toolchain.resolve_jar("/explicit.jar") == "/explicit.jar"
    monkeypatch.setenv("TLA_VERIFY_JAR", "/env.jar")
    assert toolchain.resolve_jar() == "/env.jar"


def test_resolve_jar_default_points_at_lib(monkeypatch):
    jar = toolchain.resolve_jar()
    assert jar.endswith("lib/tla2tools.jar")


def test_java_major_version_modern(monkeypatch):
    class P:
        stderr = 'openjdk version "17.0.10" 2024-01-16\n'
        stdout = ""
    monkeypatch.setattr(toolchain.subprocess, "run", lambda *a, **k: P())
    assert toolchain.java_major_version("/any/java") == "17"


def test_java_major_version_legacy_eight(monkeypatch):
    class P:
        stderr = 'java version "1.8.0_321"\n'
        stdout = ""
    monkeypatch.setattr(toolchain.subprocess, "run", lambda *a, **k: P())
    assert toolchain.java_major_version("/any/java") == "8"


def test_java_major_version_missing(monkeypatch):
    def _boom(*a, **k):
        raise FileNotFoundError("no java")
    monkeypatch.setattr(toolchain.subprocess, "run", _boom)
    assert toolchain.java_major_version("/no/java") is None
