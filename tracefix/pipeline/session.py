"""Session recording and persistence.

Saves the full conversation trace (messages + tool calls + results)
to session.json inside the workspace directory.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from tracefix.pipeline.workspace import Workspace


# ---------------------------------------------------------------------------
# Model pricing: cost per 1M tokens (USD)
# ---------------------------------------------------------------------------

MODEL_PRICING: dict[str, dict[str, float]] = {
    # OpenAI — GPT-5 family.
    # Note: gpt-5.4 is NOT a minor update to gpt-5 — it has its own price schedule
    # (2x input, 1.5x output vs gpt-5). Confirmed against developers.openai.com/api/docs/pricing
    # in April 2026. gpt-5.4 also carries a 272K-context surcharge (input doubles to $5/M
    # above 272K input tokens) that this calculator does NOT currently model — estimates
    # below that threshold are accurate, above it they'll underestimate.
    "gpt-5":        {"input": 1.25,  "cached_input": 0.125, "output": 10.0},
    "gpt-5-mini":   {"input": 0.25,  "cached_input": 0.025, "output": 2.0},
    "gpt-5-nano":   {"input": 0.10,  "cached_input": 0.01,  "output": 0.40},
    "gpt-5.4":      {"input": 2.50,  "cached_input": 0.25,  "output": 15.0},
    # Earlier preview snapshot referenced in docs/notes/RESEARCH.md — priced as gpt-5 until
    # confirmed otherwise (it predates the gpt-5.4 re-price).
    "gpt-5.2":      {"input": 1.25,  "cached_input": 0.125, "output": 10.0},
    "gpt-4.1":      {"input": 2.00,  "cached_input": 0.50,  "output": 8.0},
    "gpt-4.1-mini": {"input": 0.40,  "cached_input": 0.10,  "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10,  "cached_input": 0.025, "output": 0.40},
    # Anthropic
    "claude-sonnet-4-20250514":  {"input": 3.0, "cached_input": 0.30, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 1.0, "cached_input": 0.10, "output": 5.0},
}


def _resolve_pricing(model: str) -> dict[str, float] | None:
    """Look up pricing with a conservative fallback.

    Precedence:
      1. Exact match in MODEL_PRICING.
      2. Strip OpenRouter-style provider prefix ("openai/gpt-5.4" → "gpt-5.4").
      3. Same-family fallback for undated sub-variants, preserving the major version's
         pricing schedule:
           gpt-5.4-*  → gpt-5.4   (gpt-5.4-mini/-nano/-pro not explicitly listed)
           gpt-5-*    → gpt-5     (excluding already-listed -mini/-nano)
           gpt-4.1-*  → gpt-4.1
      4. Otherwise return None (caller marks cost_known=False).

    We deliberately do NOT fold gpt-5.x into the gpt-5 schedule: gpt-5.4 is ~2x the
    input rate and 1.5x the output rate of gpt-5, so prefix collapse would silently
    underestimate cost.
    """
    if not model:
        return None
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    # OpenRouter prefix like "openai/gpt-5.4"
    if "/" in model:
        bare = model.split("/", 1)[1]
        if bare in MODEL_PRICING:
            return MODEL_PRICING[bare]
        model = bare
    # Dotted major versions: match the longest known prefix first so gpt-5.4-mini
    # maps to gpt-5.4, not to gpt-5.
    for candidate in ("gpt-5.4", "gpt-5.2", "gpt-4.1"):
        if model.startswith(candidate + "-") or model.startswith(candidate + "."):
            return MODEL_PRICING.get(candidate)
    # Dashed variants: gpt-5-foo (not -mini/-nano which are exact matches above)
    if model.startswith("gpt-5-") or model.startswith("gpt-5."):
        return MODEL_PRICING.get("gpt-5")
    return None


def _estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int,
) -> float:
    """Estimate API cost in USD from token counts.

    Returns 0.0 if model pricing is unknown (after prefix fallback).
    """
    pricing = _resolve_pricing(model)
    if pricing is None:
        return 0.0

    # Cached tokens are a subset of prompt tokens — charged at cached_input rate
    non_cached = max(0, prompt_tokens - cached_tokens)
    cost = (
        non_cached * pricing["input"] / 1_000_000
        + cached_tokens * pricing["cached_input"] / 1_000_000
        + completion_tokens * pricing["output"] / 1_000_000
    )
    return round(cost, 6)


def estimate_run_cost(
    workspace: Workspace,
    primary_model: str,
    summarizer_model: str = "",
) -> dict:
    """Public helper: total cost breakdown for a workspace run.

    Splits primary (agent loop) and summarizer (context compression) tokens so
    each is priced at its own model's rate. Returns a dict with tokens + USD
    breakdown; `cost_known` is False if neither model has pricing data.
    """
    primary_cost = _estimate_cost(
        primary_model,
        workspace.total_prompt_tokens,
        workspace.total_completion_tokens,
        workspace.total_cached_tokens,
    )
    summ_prompt = workspace.summarizer_prompt_tokens
    summ_completion = workspace.summarizer_completion_tokens
    summ_cached = workspace.summarizer_cached_tokens
    summarizer_cost = _estimate_cost(
        summarizer_model, summ_prompt, summ_completion, summ_cached,
    ) if summarizer_model else 0.0

    primary_known = _resolve_pricing(primary_model) is not None
    summarizer_known = (
        not summarizer_model or _resolve_pricing(summarizer_model) is not None
    )

    return {
        "primary_model": primary_model,
        "primary_prompt_tokens": workspace.total_prompt_tokens,
        "primary_completion_tokens": workspace.total_completion_tokens,
        "primary_cached_tokens": workspace.total_cached_tokens,
        "primary_cost_usd": primary_cost,
        "summarizer_model": summarizer_model,
        "summarizer_prompt_tokens": summ_prompt,
        "summarizer_completion_tokens": summ_completion,
        "summarizer_cached_tokens": summ_cached,
        "summarizer_cost_usd": summarizer_cost,
        "total_cost_usd": round(primary_cost + summarizer_cost, 6),
        "cost_known": primary_known and summarizer_known,
    }


def format_run_cost(cost: dict) -> str:
    """One-line human-readable summary suitable for CLI output."""
    total_primary = cost["primary_prompt_tokens"] + cost["primary_completion_tokens"]
    total_summ = cost["summarizer_prompt_tokens"] + cost["summarizer_completion_tokens"]
    warn = "" if cost["cost_known"] else "  (* pricing estimate — unknown model)"
    parts = [
        f"Primary ({cost['primary_model']}): "
        f"{total_primary:,} tok ({cost['primary_prompt_tokens']:,} in / "
        f"{cost['primary_completion_tokens']:,} out"
        + (f" / {cost['primary_cached_tokens']:,} cached" if cost["primary_cached_tokens"] else "")
        + f") = ${cost['primary_cost_usd']:.4f}"
    ]
    if cost["summarizer_model"] and total_summ > 0:
        parts.append(
            f"Summarizer ({cost['summarizer_model']}): "
            f"{total_summ:,} tok = ${cost['summarizer_cost_usd']:.4f}"
        )
    parts.append(f"Total: ${cost['total_cost_usd']:.4f}{warn}")
    return " | ".join(parts)


@dataclass
class SessionRecord:
    """A complete record of one agent session."""

    session_id: str
    start_time: str
    end_time: str = ""
    config: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    task_id: str | None = None
    messages: list[dict] = field(default_factory=list)
    final_text: str = ""
    result: dict = field(default_factory=dict)
    workspace_snapshot: dict = field(default_factory=dict)
    files: list[str] = field(default_factory=list)

    def save(self, workspace: Workspace) -> Path:
        """Save session to session.json inside the workspace directory.

        Returns:
            Path to the saved file.
        """
        filepath = workspace.path("session.json")

        data = asdict(self)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        return filepath

    @classmethod
    def create(
        cls,
        config: dict,
        workspace: Workspace,
        messages: list[dict],
        final_text: str,
        start_time: datetime,
        task_id: str | None = None,
    ) -> SessionRecord:
        """Create a SessionRecord from a completed agent loop."""
        now = datetime.now()
        elapsed = (now - start_time).total_seconds()

        # Redact API key from config
        safe_config = {k: v for k, v in config.items() if k != "api_key"}
        safe_config["api_key"] = "***"

        # Build real-time stats block.
        # Split primary (agent loop) vs summarizer (context compression) costs so
        # each is priced at its own model's rate.
        model = config.get("model", "")
        summarizer_model = config.get("summarizer_model", "")
        cost = estimate_run_cost(workspace, model, summarizer_model)
        stats = {
            "prompt_tokens": workspace.total_prompt_tokens,
            "completion_tokens": workspace.total_completion_tokens,
            "cached_tokens": workspace.total_cached_tokens,
            "total_tokens": workspace.total_prompt_tokens + workspace.total_completion_tokens,
            "summarizer_prompt_tokens": workspace.summarizer_prompt_tokens,
            "summarizer_completion_tokens": workspace.summarizer_completion_tokens,
            "summarizer_cached_tokens": workspace.summarizer_cached_tokens,
            "tool_calls": workspace.total_tool_calls,
            "repairs": workspace.repair_count,
            "turns": _count_turns(messages),
            "elapsed_seconds": round(elapsed, 1),
            "estimated_cost_usd": cost["total_cost_usd"],
            "primary_cost_usd": cost["primary_cost_usd"],
            "summarizer_cost_usd": cost["summarizer_cost_usd"],
            "cost_known": cost["cost_known"],
            "passed": workspace.result.final_passed,
            "tlc_status": workspace.result.tlc_status or "",
            "violation_type": workspace.result.tlc_violation_type,
        }

        return cls(
            session_id=workspace.session_id,
            start_time=start_time.isoformat(),
            end_time=now.isoformat(),
            config=safe_config,
            stats=stats,
            task_id=task_id,
            messages=messages,
            final_text=final_text,
            result=workspace.result.to_dict(),
            workspace_snapshot=workspace.snapshot(),
            files=workspace.list_files(),
        )


def _count_turns(messages: list[dict]) -> int:
    """Count agent turns (assistant messages with tool calls)."""
    return sum(
        1 for m in messages
        if m.get("role") == "assistant" and m.get("tool_calls")
    )
