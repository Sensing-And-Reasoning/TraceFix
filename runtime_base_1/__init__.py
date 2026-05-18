"""Baseline 1: Group chat runtime — agents communicate via shared message board.

Derives from runtime_B via the Chat Adapter pattern: ChatCoordinationContext
duck-types CoordinationContext, enabling direct reuse of AgentRunner for
experimental fairness (same LLM client, retry logic, concurrent execution).
"""
