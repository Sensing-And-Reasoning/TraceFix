"""Load the repo-root ``.env`` so runtime CLIs authenticate without a manual export.

The runtime ``run`` commands run LLM agents — either in-process (the monitoring
OpenAI loop) or as spawned child processes (opencode) — which need
``OPENAI_API_KEY`` / ``OPENROUTER_API_KEY`` / ``ANTHROPIC_API_KEY`` in their
environment. Without loading the repo ``.env`` first, those agents inherit no keys
and every one fails authentication before its first tool call (the run reports
"0 tool calls, error" per agent, and the monitor looks misleadingly "clean" because
no coordination op ever ran). Mirrors the pipeline CLI's ``.env`` load.

The coordination *service* CLI deliberately does NOT call this — the authority node
makes no LLM calls, so it needs no provider keys. ``sdk_adapter`` has historically
done its own inline load; it may migrate to this helper.
"""

from __future__ import annotations

from pathlib import Path

# tracefix/runtime/env_setup.py → parents[2] == repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]


def load_repo_env() -> None:
    """Load ``<repo-root>/.env`` into ``os.environ`` without overriding existing vars.

    No-op (and never raises) if python-dotenv or the ``.env`` file is absent, so a
    user who already exported their keys — or installed without dotenv — is
    unaffected. ``load_dotenv`` defaults to ``override=False``, so a real exported
    environment variable always wins over the file.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = _REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
