"""End-to-end tests for tracefix.pipeline/loop.py using mock LLM clients."""

import json

import pytest

from tracefix.pipeline.workspace import Workspace
from tracefix.pipeline.tool_client import AgentResponse, ToolCall
from tracefix.pipeline.loop import AgentLoop


# ---------------------------------------------------------------------------
# Mock tool client
# ---------------------------------------------------------------------------

class MockToolClient:
    """Mock ToolClient that returns pre-defined AgentResponse sequences.

    When call_count exceeds the response list, returns the last response.
    """

    def __init__(self, responses: list[AgentResponse]):
        self._responses = responses
        self.call_count = 0
        self.received_messages: list[list[dict]] = []

    def chat(self, messages: list[dict]) -> AgentResponse:
        self.received_messages.append(list(messages))
        idx = min(self.call_count, len(self._responses) - 1)
        resp = self._responses[idx]
        self.call_count += 1
        return resp


def _make_response(
    text: str | None = None,
    tool_calls: list[ToolCall] | None = None,
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
) -> AgentResponse:
    """Helper to create an AgentResponse."""
    return AgentResponse(
        text=text,
        tool_calls=tool_calls or [],
        usage={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cached_tokens": 0,
        },
    )


@pytest.fixture
def ws(tmp_path):
    return Workspace(session_id="loop_test", base_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# Normal termination
# ---------------------------------------------------------------------------

class TestNormalTermination:
    def test_agent_finishes_with_no_tool_calls(self, ws):
        """Agent returns text with no tool calls — loop exits normally."""
        client = MockToolClient([
            _make_response(text="All done!", tool_calls=[]),
        ])
        loop = AgentLoop(client, ws, system_prompt="You are a test agent.", max_turns=10)
        result = loop.run("Do something.")
        assert result == "All done!"
        assert client.call_count == 1

    def test_tool_call_then_finish(self, ws):
        """Agent calls list_files on turn 1, then finishes on turn 2."""
        client = MockToolClient([
            _make_response(
                text=None,
                tool_calls=[ToolCall(id="tc1", name="list_files", arguments={})],
            ),
            _make_response(text="Done listing.", tool_calls=[]),
        ])
        loop = AgentLoop(client, ws, system_prompt="Test", max_turns=10)
        result = loop.run("List files")
        assert result == "Done listing."
        assert client.call_count == 2
        assert ws.total_tool_calls == 1

    def test_multiple_tool_calls_then_finish(self, ws):
        """Agent calls write_file then list_files, then finishes."""
        client = MockToolClient([
            _make_response(
                tool_calls=[
                    ToolCall(id="tc1", name="write_file",
                             arguments={"path": "test.txt", "content": "hello"}),
                ],
            ),
            _make_response(
                tool_calls=[
                    ToolCall(id="tc2", name="list_files", arguments={}),
                ],
            ),
            _make_response(text="Completed."),
        ])
        loop = AgentLoop(client, ws, system_prompt="Test", max_turns=10)
        result = loop.run("Write and list")
        assert result == "Completed."
        assert client.call_count == 3
        assert ws.total_tool_calls == 2
        assert ws.read_file("test.txt") == "hello"


# ---------------------------------------------------------------------------
# Max turns limit
# ---------------------------------------------------------------------------

class TestMaxTurns:
    def test_max_turns_reached(self, ws):
        """Agent always returns tool calls — loop exits at max_turns."""
        client = MockToolClient([
            _make_response(
                tool_calls=[ToolCall(id="tc_x", name="list_files", arguments={})],
            ),
        ])
        loop = AgentLoop(client, ws, system_prompt="Test", max_turns=3)
        result = loop.run("Keep going forever")
        assert "maximum turns" in result.lower() or client.call_count == 3
        assert client.call_count == 3

    def test_max_turns_1(self, ws):
        """With max_turns=1, agent gets exactly 1 turn."""
        client = MockToolClient([
            _make_response(
                tool_calls=[ToolCall(id="tc1", name="list_files", arguments={})],
            ),
        ])
        loop = AgentLoop(client, ws, system_prompt="Test", max_turns=1)
        result = loop.run("One turn only")
        assert client.call_count == 1


# ---------------------------------------------------------------------------
# Doom loop detection
# ---------------------------------------------------------------------------

class TestDoomLoop:
    def test_doom_loop_detection(self, ws):
        """Consecutive same-tool calls trigger doom loop error."""
        client = MockToolClient([
            _make_response(
                tool_calls=[ToolCall(id=f"tc{i}", name="list_files", arguments={})],
            )
            for i in range(10)
        ] + [_make_response(text="done")])

        loop = AgentLoop(
            client, ws, system_prompt="Test",
            max_turns=10, max_consecutive_same_tool=3,
        )
        result = loop.run("Do something")

        # After 3 consecutive list_files calls, doom loop should trigger
        # The 4th call should return an error
        messages = client.received_messages
        # Find the doom loop error in messages
        doom_found = False
        for msg_list in messages:
            for msg in msg_list:
                content = msg.get("content", "")
                if "ERROR" in content and "consecutively" in content:
                    doom_found = True
                    break
        assert doom_found

    def test_no_doom_loop_when_disabled(self, ws):
        """With max_consecutive_same_tool=0, no doom loop detection."""
        client = MockToolClient([
            _make_response(
                tool_calls=[ToolCall(id=f"tc{i}", name="list_files", arguments={})],
            )
            for i in range(5)
        ] + [_make_response(text="done")])

        loop = AgentLoop(
            client, ws, system_prompt="Test",
            max_turns=6, max_consecutive_same_tool=0,
        )
        result = loop.run("No doom check")
        # All calls should succeed without doom loop error
        assert client.call_count == 6


# ---------------------------------------------------------------------------
# Context compression (truncation-based, no summarizer)
# ---------------------------------------------------------------------------

class TestContextCompression:
    def test_truncation_compression_triggers(self, ws):
        """Large tool results trigger context compression."""
        big_content = "x" * 5000
        client = MockToolClient([
            _make_response(
                tool_calls=[
                    ToolCall(id="tc1", name="write_file",
                             arguments={"path": "big.txt", "content": big_content}),
                ],
            ),
            _make_response(
                tool_calls=[
                    ToolCall(id="tc2", name="read_file",
                             arguments={"path": "big.txt"}),
                ],
            ),
            _make_response(text="Done."),
        ])

        loop = AgentLoop(
            client, ws, system_prompt="Test",
            max_turns=5,
            context_limit_chars=500,  # Very low limit to trigger compression
            max_result_chars=200,
        )
        result = loop.run("Write and read big file")
        assert result == "Done."

    def test_result_truncation(self, ws):
        """Long tool results are truncated in message history."""
        from tracefix.pipeline.tools import write_file
        write_file(ws, path="big.txt", content="y" * 5000)

        client = MockToolClient([
            _make_response(
                tool_calls=[
                    ToolCall(id="tc1", name="read_file",
                             arguments={"path": "big.txt"}),
                ],
            ),
            _make_response(text="Got it."),
        ])

        loop = AgentLoop(
            client, ws, system_prompt="Test",
            max_turns=3,
            max_result_chars=100,
        )
        result = loop.run("Read big file")
        assert result == "Got it."

        # Check that stored tool result was truncated
        tool_results = [m for m in loop.messages if m.get("role") == "tool_result"]
        assert len(tool_results) == 1
        assert len(tool_results[0]["content"]) < 5000
        assert "truncated" in tool_results[0]["content"]


# ---------------------------------------------------------------------------
# Parallel tool execution
# ---------------------------------------------------------------------------

class TestParallelExecution:
    def test_multiple_read_only_tools(self, ws):
        """Multiple read-only tool calls should all execute."""
        from tracefix.pipeline.tools import write_file
        write_file(ws, path="a.txt", content="aaa")
        write_file(ws, path="b.txt", content="bbb")

        client = MockToolClient([
            _make_response(
                tool_calls=[
                    ToolCall(id="tc1", name="read_file", arguments={"path": "a.txt"}),
                    ToolCall(id="tc2", name="read_file", arguments={"path": "b.txt"}),
                    ToolCall(id="tc3", name="list_files", arguments={}),
                ],
            ),
            _make_response(text="All read."),
        ])

        loop = AgentLoop(client, ws, system_prompt="Test", max_turns=5)
        result = loop.run("Read everything")
        assert result == "All read."
        assert ws.total_tool_calls == 3

        # All 3 tool results should be in messages
        tool_results = [m for m in loop.messages if m.get("role") == "tool_result"]
        assert len(tool_results) == 3


# ---------------------------------------------------------------------------
# Token tracking
# ---------------------------------------------------------------------------

class TestTokenTracking:
    def test_tokens_accumulate(self, ws):
        """Token usage accumulates across turns."""
        client = MockToolClient([
            _make_response(
                tool_calls=[ToolCall(id="tc1", name="list_files", arguments={})],
                prompt_tokens=200, completion_tokens=100,
            ),
            _make_response(
                text="Done.",
                prompt_tokens=300, completion_tokens=50,
            ),
        ])

        loop = AgentLoop(client, ws, system_prompt="Test", max_turns=5)
        loop.run("Track tokens")

        assert ws.total_prompt_tokens == 500  # 200 + 300
        assert ws.total_completion_tokens == 150  # 100 + 50


# ---------------------------------------------------------------------------
# Unknown tool handling
# ---------------------------------------------------------------------------

class TestUnknownTool:
    def test_unknown_tool_returns_error(self, ws):
        """Calling a non-existent tool returns an error message."""
        client = MockToolClient([
            _make_response(
                tool_calls=[ToolCall(id="tc1", name="nonexistent_tool", arguments={})],
            ),
            _make_response(text="OK."),
        ])

        loop = AgentLoop(client, ws, system_prompt="Test", max_turns=5)
        result = loop.run("Try unknown tool")
        assert result == "OK."

        # Check the error was returned
        tool_results = [m for m in loop.messages if m.get("role") == "tool_result"]
        assert len(tool_results) == 1
        assert "ERROR" in tool_results[0]["content"]
        assert "Unknown tool" in tool_results[0]["content"]


# ---------------------------------------------------------------------------
# On-turn-end callback
# ---------------------------------------------------------------------------

class TestOnTurnEnd:
    def test_callback_invoked(self, ws):
        """on_turn_end callback is called after each turn."""
        call_count = [0]

        def callback(loop):
            call_count[0] += 1

        client = MockToolClient([
            _make_response(
                tool_calls=[ToolCall(id="tc1", name="list_files", arguments={})],
            ),
            _make_response(text="Done."),
        ])

        loop = AgentLoop(
            client, ws, system_prompt="Test",
            max_turns=5, on_turn_end=callback,
        )
        loop.run("With callback")
        # Callback fires after tool execution turns, not the final no-tool turn
        assert call_count[0] == 1

    def test_callback_exception_does_not_crash(self, ws):
        """on_turn_end callback exceptions are swallowed."""
        def bad_callback(loop):
            raise RuntimeError("callback failed")

        client = MockToolClient([
            _make_response(
                tool_calls=[ToolCall(id="tc1", name="list_files", arguments={})],
            ),
            _make_response(text="Done."),
        ])

        loop = AgentLoop(
            client, ws, system_prompt="Test",
            max_turns=5, on_turn_end=bad_callback,
        )
        result = loop.run("Bad callback")
        assert result == "Done."  # Should not crash
