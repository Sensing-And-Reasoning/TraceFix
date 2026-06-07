"""Tests for the repo-root .env loader used by the runtime CLIs."""

import os

from tracefix.runtime.env_setup import load_repo_env, _REPO_ROOT


def test_repo_root_points_at_repo():
    """parents[2] must resolve to the repo root (sanity: it holds pyproject.toml)."""
    assert (_REPO_ROOT / "pyproject.toml").is_file()


def test_load_repo_env_does_not_override_existing(monkeypatch):
    """An already-exported var must win over the .env file (load_dotenv override=False)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sentinel-already-set")
    load_repo_env()
    assert os.environ["OPENAI_API_KEY"] == "sentinel-already-set"


def test_load_repo_env_is_safe_and_idempotent():
    """Never raises, regardless of dotenv/.env presence; callable repeatedly."""
    load_repo_env()
    load_repo_env()
