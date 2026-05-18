"""Tests for LLMPolicy — mocked LLM, no network calls."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tracefix.runtime.enforcement.llm_policy import (
    LLMPolicy,
    _AgentLoop,
    _extract_options,
    _format_context,
    _match_choice,
)


# ---------------------------------------------------------------------------
# Helper: build a fake OpenAI response
# ---------------------------------------------------------------------------

def _make_response(tool_calls=None, content=""):
    """Build a minimal ChatCompletion-like response object."""
    tc_objs = []
    if tool_calls:
        for i, (name, args) in enumerate(tool_calls):
            tc_objs.append(SimpleNamespace(
                id=f"call_{i}",
                function=SimpleNamespace(
                    name=name,
                    arguments=json.dumps(args),
                ),
            ))
    msg = SimpleNamespace(
        content=content,
        tool_calls=tc_objs if tc_objs else None,
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


# ---------------------------------------------------------------------------
# _extract_options
# ---------------------------------------------------------------------------

class TestExtractOptions:
    def test_send_labels(self):
        actions = [
            {"target": "s1", "send": [{"channel": "ch", "label": "go"}]},
            {"target": "s2", "send": [{"channel": "ch", "label": "no_go"}]},
        ]
        assert _extract_options(actions) == ["go", "no_go"]

    def test_target_names(self):
        actions = [
            {"target": "state_a"},
            {"target": "state_b"},
        ]
        assert _extract_options(actions) == ["state_a", "state_b"]

    def test_mixed(self):
        actions = [
            {"target": "s1", "send": [{"channel": "ch", "label": "approve"}]},
            {"target": "reject_state"},
        ]
        assert _extract_options(actions) == ["approve", "reject_state"]

    def test_empty_send_list(self):
        actions = [{"target": "t1", "send": []}]
        assert _extract_options(actions) == ["t1"]


# ---------------------------------------------------------------------------
# _match_choice
# ---------------------------------------------------------------------------

class TestMatchChoice:
    def test_exact_match(self):
        options = ["go", "no_go"]
        actions = [{"target": "s1"}, {"target": "s2"}]
        assert _match_choice("go", options, actions) == 0
        assert _match_choice("no_go", options, actions) == 1

    def test_case_insensitive(self):
        options = ["Go", "No_Go"]
        actions = [{"target": "s1"}, {"target": "s2"}]
        assert _match_choice("go", options, actions) == 0
        assert _match_choice("NO_GO", options, actions) == 1

    def test_fallback(self):
        options = ["go", "no_go"]
        actions = [{"target": "s1"}, {"target": "s2"}]
        assert _match_choice("invalid", options, actions) == 0


# ---------------------------------------------------------------------------
# _format_context
# ---------------------------------------------------------------------------

class TestFormatContext:
    def test_none(self):
        assert _format_context(None) == ""

    def test_empty(self):
        assert _format_context([]) == ""

    def test_single_step(self):
        ctx = [{"from": "a1", "to": "a2", "guards": ["acquire(lock)"], "effects": []}]
        result = _format_context(ctx)
        assert "a1→a2" in result
        assert "acquire(lock)" in result

    def test_multiple_steps(self):
        ctx = [
            {"from": "a1", "to": "a2", "guards": [], "effects": ["send(ch,msg)"]},
            {"from": "a2", "to": "a3", "guards": ["recv(ch2,ack)"], "effects": []},
        ]
        result = _format_context(ctx)
        assert "a1→a2" in result
        assert "a2→a3" in result
        assert "send(ch,msg)" in result
        assert "recv(ch2,ack)" in result


# ---------------------------------------------------------------------------
# LLMPolicy.choose_action (via _AgentLoop)
# ---------------------------------------------------------------------------

class TestLLMPolicySingleAction:
    def test_single_action_calls_llm_for_domain_work(self):
        """Single action still calls LLM so it can execute domain tools."""
        policy = LLMPolicy(
            prompts={"agent_a": "You are test agent A."},
            model="test-model",
            api_key="fake-key",
        )
        responses = [
            _make_response(tool_calls=[("respond_decision", {"choice": "next"})]),
        ]
        policy._call_openai = MagicMock(side_effect=responses)
        actions = [{"target": "next"}]

        idx, tool_calls = asyncio.run(
            policy.choose_action("agent_a", "state_1", actions)
        )
        assert idx == 0
        policy._call_openai.assert_called_once()

    def test_single_action_with_domain_tool(self):
        """Single action: LLM calls a domain tool, then respond_decision."""
        policy = LLMPolicy(
            prompts={"agent_a": "You are test agent A."},
            model="test-model",
            api_key="fake-key",
        )
        responses = [
            # First response: call domain tool
            _make_response(tool_calls=[("run_stepper_exposure", {"process": "photo"})]),
            # Second response: signal decision
            _make_response(tool_calls=[("respond_decision", {"choice": "next"})]),
        ]
        policy._call_openai = MagicMock(side_effect=responses)
        actions = [{"target": "next"}]

        idx, tool_calls = asyncio.run(
            policy.choose_action("agent_a", "state_1", actions)
        )
        assert idx == 0
        # Should have 2 tool calls: domain tool + respond_decision
        assert len(tool_calls) == 2
        assert tool_calls[0]["tool"] == "run_stepper_exposure"
        assert tool_calls[1]["tool"] == "respond_decision"


class TestLLMPolicyDecision:
    def _make_policy(self, mock_responses):
        """Create policy with mocked _call_openai returning successive responses."""
        policy = LLMPolicy(
            prompts={"agent_a": "You are test agent A."},
            model="test-model",
            api_key="fake-key",
        )
        policy._call_openai = MagicMock(side_effect=mock_responses)
        return policy

    def test_decision_maps_to_send_label(self):
        """LLM calls respond_decision('go') -> maps to action with send label 'go'."""
        responses = [
            _make_response(tool_calls=[("respond_decision", {"choice": "go"})]),
        ]
        policy = self._make_policy(responses)

        actions = [
            {"target": "s1", "send": [{"channel": "ch", "label": "go"}]},
            {"target": "s2", "send": [{"channel": "ch", "label": "no_go"}]},
        ]

        idx, tool_calls = asyncio.run(
            policy.choose_action("agent_a", "review_state", actions)
        )
        assert idx == 0
        assert any(tc["tool"] == "respond_decision" for tc in tool_calls)

    def test_decision_maps_to_second_option(self):
        """LLM calls respond_decision('no_go') -> maps to index 1."""
        responses = [
            _make_response(tool_calls=[("respond_decision", {"choice": "no_go"})]),
        ]
        policy = self._make_policy(responses)

        actions = [
            {"target": "s1", "send": [{"channel": "ch", "label": "go"}]},
            {"target": "s2", "send": [{"channel": "ch", "label": "no_go"}]},
        ]

        idx, _ = asyncio.run(
            policy.choose_action("agent_a", "review_state", actions)
        )
        assert idx == 1

    def test_decision_maps_to_target(self):
        """LLM calls respond_decision with target state name."""
        responses = [
            _make_response(tool_calls=[
                ("respond_decision", {"choice": "ls_rcv_bio_first"}),
            ]),
        ]
        policy = self._make_policy(responses)

        actions = [
            {"target": "ls_rcv_bio_first"},
            {"target": "ls_rcv_chem_first"},
        ]

        idx, _ = asyncio.run(
            policy.choose_action("agent_a", "decide_state", actions)
        )
        assert idx == 0

    def test_domain_tool_then_decision(self):
        """LLM calls a domain tool first, then respond_decision."""
        responses = [
            # First response: call a domain tool
            _make_response(tool_calls=[("review_code", {"file": "main.py"})]),
            # Second response: call respond_decision
            _make_response(tool_calls=[("respond_decision", {"choice": "approve"})]),
        ]
        policy = self._make_policy(responses)

        # Mock a tool registry
        mock_result = SimpleNamespace(to_dict=lambda: {"status": "ok", "quality": "good"})
        mock_registry = MagicMock()
        mock_registry.openai_schemas = MagicMock(return_value=[
            {"type": "function", "function": {"name": "review_code", "parameters": {}}},
        ])
        mock_registry.call = AsyncMock(return_value=mock_result)
        policy._tools = mock_registry

        actions = [
            {"target": "s1", "send": [{"channel": "ch", "label": "approve"}]},
            {"target": "s2", "send": [{"channel": "ch", "label": "reject"}]},
        ]

        idx, tool_calls = asyncio.run(
            policy.choose_action("agent_a", "review_state", actions)
        )
        assert idx == 0
        assert len(tool_calls) == 2
        assert tool_calls[0]["tool"] == "review_code"
        assert tool_calls[1]["tool"] == "respond_decision"

    def test_no_tool_calls_nudge(self):
        """If LLM returns no tool calls, it gets nudged then calls respond_decision."""
        responses = [
            # First: no tool calls
            _make_response(content="I think I should approve."),
            # After nudge: calls respond_decision
            _make_response(tool_calls=[("respond_decision", {"choice": "approve"})]),
        ]
        policy = self._make_policy(responses)

        actions = [
            {"target": "s1", "send": [{"channel": "ch", "label": "approve"}]},
            {"target": "s2", "send": [{"channel": "ch", "label": "reject"}]},
        ]

        idx, _ = asyncio.run(
            policy.choose_action("agent_a", "state_1", actions)
        )
        assert idx == 0


# ---------------------------------------------------------------------------
# Continuous loop: multiple choose_action calls share one conversation
# ---------------------------------------------------------------------------

class TestContinuousLoop:
    def test_continuous_loop_single_user_message(self):
        """Multiple choose_action calls for same agent only add 1 user message.
        Subsequent states arrive via respond_decision tool results."""
        policy = LLMPolicy(
            prompts={"agent_a": "System prompt."},
            model="test",
        )

        call_count = 0

        def mock_openai(messages, tools):
            nonlocal call_count
            call_count += 1
            # Always respond with respond_decision
            return _make_response(
                tool_calls=[("respond_decision", {"choice": "next"})]
            )

        policy._call_openai = MagicMock(side_effect=mock_openai)

        async def run():
            actions1 = [{"target": "next1"}]
            await policy.choose_action("agent_a", "state_1", actions1)

            actions2 = [{"target": "next2"}]
            await policy.choose_action("agent_a", "state_2", actions2)

            actions3 = [{"target": "next3"}]
            await policy.choose_action("agent_a", "state_3", actions3)

            await policy.notify_done("agent_a")

        asyncio.run(run())

        # Check history: should have 1 system + 1 user + (asst+tool) * 3
        loop = policy._loops["agent_a"]
        history = loop.history
        assert history[0]["role"] == "system"
        # Count user messages (only the initial one)
        user_msgs = [m for m in history if m["role"] == "user"]
        assert len(user_msgs) == 1

    def test_respond_decision_result_has_state_info(self):
        """The tool result from respond_decision should contain new_state and options."""
        policy = LLMPolicy(
            prompts={"agent_a": "System prompt."},
            model="test",
        )
        policy._call_openai = MagicMock(side_effect=[
            _make_response(tool_calls=[("respond_decision", {"choice": "next"})]),
            _make_response(tool_calls=[("respond_decision", {"choice": "approve"})]),
        ])

        async def run():
            actions1 = [{"target": "next"}]
            await policy.choose_action("agent_a", "state_1", actions1)

            actions2 = [
                {"target": "s1", "send": [{"channel": "ch", "label": "approve"}]},
                {"target": "s2", "send": [{"channel": "ch", "label": "reject"}]},
            ]
            await policy.choose_action(
                "agent_a", "state_2", actions2,
                context=[{"from": "s_auto1", "to": "s_auto2",
                          "guards": ["acquire(lock)"], "effects": []}],
            )

            await policy.notify_done("agent_a")

        asyncio.run(run())

        # Find the first tool result (after the first respond_decision)
        loop = policy._loops["agent_a"]
        history = loop.history
        tool_results = [m for m in history if m["role"] == "tool"]
        # First tool result carries state info for state_2
        first_result = json.loads(tool_results[0]["content"])
        assert first_result["status"] == "ok"
        assert first_result["new_state"] == "state_2"
        assert first_result["options"] == ["approve", "reject"]
        assert "context" in first_result  # has auto-advance context

    def test_context_passed_to_initial_message(self):
        """Auto-advance context on the first call shows up in the user message."""
        policy = LLMPolicy(
            prompts={"agent_a": "System prompt."},
            model="test",
        )
        policy._call_openai = MagicMock(side_effect=[
            _make_response(tool_calls=[("respond_decision", {"choice": "next"})]),
        ])

        async def run():
            actions = [{"target": "next"}]
            await policy.choose_action(
                "agent_a", "state_1", actions,
                context=[{"from": "s0", "to": "s1",
                          "guards": ["recv(ch,msg)"], "effects": []}],
            )
            await policy.notify_done("agent_a")

        asyncio.run(run())

        loop = policy._loops["agent_a"]
        user_msg = loop.history[1]
        assert user_msg["role"] == "user"
        assert "Auto-advanced" in user_msg["content"]
        assert "s0→s1" in user_msg["content"]

    def test_notify_done_terminates_loop(self):
        """After notify_done, the loop's background task should finish."""
        policy = LLMPolicy(
            prompts={"agent_a": "System prompt."},
            model="test",
        )
        policy._call_openai = MagicMock(side_effect=[
            _make_response(tool_calls=[("respond_decision", {"choice": "next"})]),
        ])

        async def run():
            actions = [{"target": "next"}]
            await policy.choose_action("agent_a", "state_1", actions)
            await policy.notify_done("agent_a")

            loop = policy._loops["agent_a"]
            # Task should be finished (None after stop)
            assert loop._task is None

        asyncio.run(run())

    def test_cleanup_cancels_all_loops(self):
        """cleanup() should cancel all agent loops."""
        policy = LLMPolicy(
            prompts={"a": "prompt a", "b": "prompt b"},
            model="test",
        )
        policy._call_openai = MagicMock(side_effect=[
            _make_response(tool_calls=[("respond_decision", {"choice": "x"})]),
            _make_response(tool_calls=[("respond_decision", {"choice": "y"})]),
        ])

        async def run():
            await policy.choose_action("a", "s1", [{"target": "x"}])
            await policy.choose_action("b", "s1", [{"target": "y"}])
            assert len(policy._loops) == 2
            await policy.cleanup()
            assert len(policy._loops) == 0

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Auto-advance integration with engine (classify + chain tests)
# ---------------------------------------------------------------------------

class TestAutoAdvanceClassify:
    """Test AgentRunner._classify() via engine."""

    def test_classify_auto_acquire(self):
        """Single action with acquire → auto."""
        from tracefix.runtime.enforcement.engine import AgentRunner
        enabled = [{"target": "s2", "acquire": ["lock"]}]
        assert AgentRunner._classify(enabled) == "auto"

    def test_classify_auto_send(self):
        """Single action with send → auto."""
        from tracefix.runtime.enforcement.engine import AgentRunner
        enabled = [{"target": "s2", "send": [{"channel": "ch", "label": "msg"}]}]
        assert AgentRunner._classify(enabled) == "auto"

    def test_classify_auto_receive(self):
        """Single action with receive → auto."""
        from tracefix.runtime.enforcement.engine import AgentRunner
        enabled = [{"target": "s2", "receive": [{"channel": "ch", "label": "msg"}]}]
        assert AgentRunner._classify(enabled) == "auto"

    def test_classify_auto_release(self):
        """Single action with release → auto."""
        from tracefix.runtime.enforcement.engine import AgentRunner
        enabled = [{"target": "s2", "release": ["lock"]}]
        assert AgentRunner._classify(enabled) == "auto"

    def test_classify_business(self):
        """Single action with no guards/effects → business."""
        from tracefix.runtime.enforcement.engine import AgentRunner
        enabled = [{"target": "s2"}]
        assert AgentRunner._classify(enabled) == "business"

    def test_classify_decision(self):
        """Multiple enabled actions → decision."""
        from tracefix.runtime.enforcement.engine import AgentRunner
        enabled = [
            {"target": "s2", "send": [{"channel": "ch", "label": "go"}]},
            {"target": "s3", "send": [{"channel": "ch", "label": "no_go"}]},
        ]
        assert AgentRunner._classify(enabled) == "decision"


class TestAutoAdvanceEngine:
    """Test auto-advance behavior in engine execution."""

    def test_auto_advance_skips_llm(self):
        """Coordination-only protocol should not call policy.choose_action."""
        from tracefix.runtime.enforcement.engine import run_ir
        from tracefix.runtime.enforcement.policy import RandomPolicy
        import random

        rng = random.Random(42)
        policy = RandomPolicy(rng)
        # Wrap choose_action to count calls
        original = policy.choose_action
        call_count = 0

        async def counting_choose(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return await original(*args, **kwargs)

        policy.choose_action = counting_choose

        # Simple lock acquire/release protocol — all states are AUTO or TERMINAL
        ir = {
            "agents": [{"id": "a", "initial_state": "a1"}],
            "resources": [{"id": "lock", "type": "Lock"}],
            "channels": [],
            "states": [
                {"id": "a1", "agent": "a", "actions": [
                    {"target": "a2", "acquire": ["lock"]}
                ]},
                {"id": "a2", "agent": "a", "actions": [
                    {"target": "a_done", "release": ["lock"]}
                ]},
                {"id": "a_done", "agent": "a", "actions": []},
            ],
        }
        result = run_ir(ir, seed=42, timeout=5, policy=policy)
        assert result.success
        assert result.steps == 2
        # Policy should NOT have been called — all states are auto-advance
        assert call_count == 0

    def test_auto_advance_chains_to_business(self):
        """Auto-advance through coordination, then call policy for business state."""
        from tracefix.runtime.enforcement.engine import run_ir
        from tracefix.runtime.enforcement.policy import RandomPolicy
        import random

        rng = random.Random(42)
        policy = RandomPolicy(rng)
        contexts_received = []
        original = policy.choose_action

        async def tracking_choose(*args, **kwargs):
            ctx = kwargs.get("context")
            contexts_received.append(ctx)
            return await original(*args, **kwargs)

        policy.choose_action = tracking_choose

        # acquire(lock) → BUSINESS (no guards/effects) → release(lock) → done
        ir = {
            "agents": [{"id": "a", "initial_state": "a1"}],
            "resources": [{"id": "lock", "type": "Lock"}],
            "channels": [],
            "states": [
                {"id": "a1", "agent": "a", "actions": [
                    {"target": "a_work", "acquire": ["lock"]}
                ]},
                {"id": "a_work", "agent": "a", "actions": [
                    {"target": "a_release"}
                ]},
                {"id": "a_release", "agent": "a", "actions": [
                    {"target": "a_done", "release": ["lock"]}
                ]},
                {"id": "a_done", "agent": "a", "actions": []},
            ],
        }
        result = run_ir(ir, seed=42, timeout=5, policy=policy)
        assert result.success
        assert result.steps == 3
        # Policy called once for a_work (business state)
        assert len(contexts_received) == 1
        # Context should contain the auto-advanced acquire step
        ctx = contexts_received[0]
        assert ctx is not None
        assert len(ctx) == 1
        assert ctx[0]["from"] == "a1"
        assert ctx[0]["to"] == "a_work"
        assert "acquire(lock)" in ctx[0]["guards"]

    def test_auto_advance_chain_multiple(self):
        """Multiple auto-advance steps chain together before reaching business."""
        from tracefix.runtime.enforcement.engine import run_ir
        from tracefix.runtime.enforcement.policy import RandomPolicy
        import random

        rng = random.Random(42)
        policy = RandomPolicy(rng)
        contexts_received = []
        original = policy.choose_action

        async def tracking_choose(*args, **kwargs):
            ctx = kwargs.get("context")
            contexts_received.append(ctx)
            return await original(*args, **kwargs)

        policy.choose_action = tracking_choose

        # send → recv → BUSINESS → done
        ir = {
            "agents": [
                {"id": "a", "initial_state": "a1"},
                {"id": "b", "initial_state": "b1"},
            ],
            "resources": [],
            "channels": [{"id": "ch", "from": "a", "to": "b"}],
            "states": [
                # Agent a: send then done
                {"id": "a1", "agent": "a", "actions": [
                    {"target": "a_done", "send": [{"channel": "ch", "label": "go"}]}
                ]},
                {"id": "a_done", "agent": "a", "actions": []},
                # Agent b: recv then business then done
                {"id": "b1", "agent": "b", "actions": [
                    {"target": "b_work", "receive": [{"channel": "ch", "label": "go"}]}
                ]},
                {"id": "b_work", "agent": "b", "actions": [
                    {"target": "b_done"}
                ]},
                {"id": "b_done", "agent": "b", "actions": []},
            ],
        }
        result = run_ir(ir, seed=42, timeout=5, policy=policy)
        assert result.success
        # Agent b should have had policy called once (for b_work)
        # with context containing the recv auto-advance
        b_contexts = [c for c in contexts_received
                      if c is not None and any(s["to"] == "b_work" for s in c)]
        assert len(b_contexts) == 1
        assert b_contexts[0][0]["from"] == "b1"
        assert b_contexts[0][0]["to"] == "b_work"
