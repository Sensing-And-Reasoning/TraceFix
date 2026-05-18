"""Agent policies for choosing among enabled actions at decision points.

An AgentPolicy is called by the engine whenever an agent has multiple enabled
actions (nondeterministic choice).  The policy may invoke business-logic tools
and use the results to decide which action to take.

Two built-in policies:
  - RandomPolicy: rng.choice(), no tool calls (backward-compatible default)
  - AgentPolicy protocol: async choose_action() for custom tool-driven logic
"""

from __future__ import annotations

import random
from typing import Protocol, runtime_checkable


@runtime_checkable
class AgentPolicy(Protocol):
    """Protocol for choosing among enabled actions at a decision point.

    Implementations may call external tools (async) and return the choice
    along with any tool-call records for the trace.
    """

    async def choose_action(
        self,
        agent_id: str,
        state_id: str,
        enabled_actions: list[dict],
        *,
        context: list[dict] | None = None,
    ) -> tuple[int, list[dict]]:
        """Pick one of the enabled actions.

        Args:
            agent_id: The agent making the decision.
            state_id: Current state of the agent.
            enabled_actions: List of IR action dicts whose guards are satisfied.
            context: Optional list of auto-advanced coordination steps that
                preceded this call (each dict has from/to/guards/effects).

        Returns:
            (index, tool_calls) where index is into enabled_actions and
            tool_calls is a list of dicts recording any tools invoked.
        """
        ...


class RandomPolicy:
    """Default policy: random choice, no tool calls.  Backward-compatible."""

    def __init__(self, rng: random.Random):
        self._rng = rng

    async def choose_action(
        self,
        agent_id: str,
        state_id: str,
        enabled_actions: list[dict],
        *,
        context: list[dict] | None = None,
    ) -> tuple[int, list[dict]]:
        idx = self._rng.randrange(len(enabled_actions))
        return idx, []
