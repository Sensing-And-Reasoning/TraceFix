"""Tests for the driver's JSONL event parsing + status classification (no spawn).

Event shapes mirror opencode `cli/cmd/run.ts --format json`:
``{type, timestamp, sessionID, part}`` with ``tool_use`` carrying
``part.tool`` / ``part.state.status`` / ``part.state.output|error``.
"""

import json

from tracefix.runtime.opencode_adapter.driver import AgentRunState, classify


def _tool_event(name: str, result=None, *, status: str = "completed") -> dict:
    state: dict = {"status": status}
    if status == "completed":
        state["output"] = result if isinstance(result, str) else json.dumps(result)
    else:
        state["error"] = result if isinstance(result, str) else json.dumps(result)
    return {"type": "tool_use", "timestamp": 1, "sessionID": "s",
            "part": {"type": "tool", "tool": name, "callID": "c", "state": state}}


def _text_event(text: str) -> dict:
    return {"type": "text", "part": {"type": "text", "text": text}}


def test_non_tool_events_are_counted_but_ignored():
    st = AgentRunState()
    st.feed({"type": "step_start", "part": {"type": "step-start"}})
    st.feed(_text_event("hello"))
    assert st.events == 2
    assert st.tool_calls == []
    assert not st.signaled_done


def test_signal_done_sets_completed():
    st = AgentRunState()
    st.feed(_tool_event("tracefix_signal_done", {"status": "done", "agent": "A"}))
    assert st.signaled_done and not st.premature_done
    assert classify(st, 0, timed_out=False) == "completed"


def test_signal_done_with_warning_is_premature():
    st = AgentRunState()
    st.feed(_tool_event("tracefix_signal_done",
                        {"status": "done", "agent": "A", "warning": "still holding DOC"}))
    assert st.signaled_done and st.premature_done
    assert classify(st, 0, timed_out=False) == "premature_done"


def test_out_of_order_then_correction_limit():
    st = AgentRunState()
    corrective = {"status": "error", "error": "out_of_order",
                  "legal_actions": [{"op": "acquire", "resource": "DOC"}]}
    st.feed(_tool_event("tracefix_send_message", corrective))
    st.feed(_tool_event("tracefix_send_message", corrective))
    st.feed(_tool_event("tracefix_send_message",
                        {"status": "error", "error": "correction_limit",
                         "legal_actions": []}))
    assert st.out_of_order == 2
    assert st.correction_limit
    assert classify(st, 0, timed_out=False) == "correction_failed"


def test_ordinary_coord_tool_recorded():
    st = AgentRunState()
    st.feed(_tool_event("tracefix_acquire_lock", {"status": "acquired", "lock": "DOC"}))
    assert st.tool_calls[-1] == {"tool": "tracefix_acquire_lock",
                                 "status": "completed", "result_status": "acquired"}
    assert not st.signaled_done


def test_done_detected_by_result_status_even_if_name_differs():
    st = AgentRunState()
    st.feed(_tool_event("weird_name", {"status": "done"}))
    assert st.signaled_done


def test_tool_with_non_json_output_is_safe():
    st = AgentRunState()
    st.feed(_tool_event("bash", "tracefix-probe\n"))   # plain text output
    assert st.tool_calls[-1]["tool"] == "bash"
    assert not st.signaled_done and not st.correction_limit


def test_classify_matrix():
    empty = AgentRunState()
    assert classify(empty, 0, timed_out=False) == "incomplete"
    assert classify(empty, 1, timed_out=False) == "error"
    assert classify(empty, 0, timed_out=True) == "timeout"

    done = AgentRunState(); done.signaled_done = True
    assert classify(done, 0, timed_out=False) == "completed"
    # timeout wins over a completion signal
    assert classify(done, 0, timed_out=True) == "timeout"

    cap = AgentRunState(); cap.correction_limit = True
    assert classify(cap, 0, timed_out=False) == "correction_failed"
