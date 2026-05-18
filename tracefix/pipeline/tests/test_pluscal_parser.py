"""Tests for pluscal_parser — PlusCal source → IR v3 states extraction.

Structured as:
  1. Unit tests: CST helpers and individual parsing functions
  2. Integration tests: full parse of specific scenarios (9E, 10E, 3E, 7H, 8E, 4M, 11M)
  3. Cross-validation: all available IRs matched against tla_parser output
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from tracefix.pipeline.pipeline.pluscal_parser import (
    parse_pluscal,
    lint_adjacent_acquire_release,
    _get_parser,
    _find_pcal_algorithm,
    _extract_processes,
    _walk_body_stmts,
    _extract_if_condition_info,
    _interpret_stmts,
    _interpret_macro_call,
    _extract_macro_args,
    _body_has_labels,
    _control_has_internal_labels,
    _node_text,
    _find_child,
    _find_children,
    LabelBlock,
    StmtEffects,
    ProcessInfo,
)
from tracefix.pipeline.pipeline.tla_parser import (
    ParseResult,
    build_ir_metadata,
    parse_translated_tla,
    _merge_receive_dispatch,
    _embed_inline_labels,
)

IR_BASE = Path(__file__).parent / "fixtures"


def _load_case(case_id: str) -> tuple[str, dict]:
    """Load a test case's TLA+ content and IR data."""
    case_dir = IR_BASE / case_id
    tla_content = (case_dir / "Protocol_translated.tla").read_text()
    ir_data = json.loads((case_dir / "ir.json").read_text())
    return tla_content, ir_data


def _available_cases() -> list[str]:
    """List all IR directories that have both Protocol_translated.tla and ir.json."""
    if not IR_BASE.exists():
        return []
    cases = []
    for d in sorted(os.listdir(IR_BASE)):
        if (IR_BASE / d / "Protocol_translated.tla").exists() and \
           (IR_BASE / d / "ir.json").exists():
            cases.append(d)
    return cases


# ===================================================================
# Unit tests: tree-sitter setup
# ===================================================================

class TestTreeSitterSetup:
    def test_parser_creation(self):
        parser = _get_parser()
        assert parser is not None

    def test_parser_cached(self):
        p1 = _get_parser()
        p2 = _get_parser()
        assert p1 is p2

    def test_parse_simple_tla(self):
        parser = _get_parser()
        source = b"---- MODULE Test ----\n===="
        tree = parser.parse(source)
        assert tree.root_node is not None
        assert tree.root_node.type == "source_file"


# ===================================================================
# Unit tests: PlusCal algorithm detection
# ===================================================================

class TestFindPcalAlgorithm:
    def test_finds_algorithm_in_9e(self):
        tla, _ = _load_case("9E")
        parser = _get_parser()
        tree = parser.parse(tla.encode())
        algo = _find_pcal_algorithm(tree)
        assert algo is not None
        assert algo.type == "pcal_algorithm"

    def test_no_algorithm_in_plain_tla(self):
        parser = _get_parser()
        tree = parser.parse(b"---- MODULE Test ----\n====")
        algo = _find_pcal_algorithm(tree)
        assert algo is None


# ===================================================================
# Unit tests: macro argument extraction
# ===================================================================

class TestMacroArgExtraction:
    def _parse_and_find_macro(self, code: str) -> tuple:
        """Parse PlusCal code and find the first macro call node."""
        tla = f"""---- MODULE T ----
(* --algorithm T {{
fair process (p_proc \\in {{P}})
variables msg = "";
{{
  lbl:
    {code}
}}
}} *)
===="""
        parser = _get_parser()
        source = tla.encode()
        tree = parser.parse(source)
        algo = _find_pcal_algorithm(tree)
        # Find first pcal_macro_call in tree
        def find_macro(node):
            if node.type == "pcal_macro_call":
                return node
            for c in node.children:
                r = find_macro(c)
                if r:
                    return r
            return None
        return find_macro(algo), source

    def test_send_args(self):
        node, source = self._parse_and_find_macro('send(ch_a, "hello");')
        args = _extract_macro_args(node, source)
        assert args == ["ch_a", '"hello"']

    def test_receive_args(self):
        node, source = self._parse_and_find_macro("receive(ch_b, msg);")
        args = _extract_macro_args(node, source)
        assert args == ["ch_b", "msg"]

    def test_acquire_lock_args(self):
        node, source = self._parse_and_find_macro("acquire_lock(my_lock);")
        args = _extract_macro_args(node, source)
        assert args == ["my_lock"]


# ===================================================================
# Unit tests: IF condition analysis
# ===================================================================

class TestIfConditionAnalysis:
    def _parse_condition(self, cond_text: str):
        """Parse a condition expression and analyze it."""
        tla = f"""---- MODULE T ----
(* --algorithm T {{
fair process (p_proc \\in {{P}})
variables msg = "";
{{
  lbl:
    if ({cond_text}) {{ skip; }};
}}
}} *)
===="""
        parser = _get_parser()
        source = tla.encode()
        tree = parser.parse(source)
        algo = _find_pcal_algorithm(tree)
        # Find pcal_if
        def find_if(node):
            if node.type == "pcal_if":
                return node
            for c in node.children:
                r = find_if(c)
                if r:
                    return r
            return None
        if_node = find_if(algo)
        # Get condition
        in_parens = False
        cond_node = None
        for c in if_node.children:
            if c.type == "(":
                in_parens = True
                continue
            if c.type == ")":
                break
            if in_parens:
                cond_node = c
                break
        return _extract_if_condition_info(cond_node, source)

    def test_string_equality(self):
        label, cond_var, guard = self._parse_condition('msg = "approve"')
        assert label == "approve"
        assert cond_var == "msg"
        assert guard is None

    def test_string_equality_reversed(self):
        label, cond_var, guard = self._parse_condition('"reject" = msg')
        assert label == "reject"
        assert cond_var == "msg"
        assert guard is None

    def test_numeric_comparison(self):
        label, cond_var, guard = self._parse_condition("count < 3")
        assert label is None
        assert cond_var is None
        assert guard == {"var": "count", "op": "<", "value": 3}

    def test_non_matching_condition(self):
        """Complex conditions that don't match known patterns."""
        label, cond_var, guard = self._parse_condition("TRUE")
        assert label is None
        assert cond_var is None
        assert guard is None


# ===================================================================
# Unit tests: label block extraction
# ===================================================================

class TestLabelBlockExtraction:
    def _get_blocks(self, body_code: str, scope_exit: str = "__done__") -> list[LabelBlock]:
        """Parse PlusCal body code and extract label blocks."""
        tla = f"""---- MODULE T ----
(* --algorithm T {{
fair process (p_proc \\in {{P}})
variables msg = "";
{{
{body_code}
}}
}} *)
===="""
        parser = _get_parser()
        source = tla.encode()
        tree = parser.parse(source)
        algo = _find_pcal_algorithm(tree)
        proc = _find_children(algo, "pcal_process")[0]
        body = _find_child(proc, "pcal_algorithm_body")
        return _walk_body_stmts(body, source, scope_exit=scope_exit)

    def test_sequential_labels(self):
        blocks = self._get_blocks("""
  step1:
    skip;
  step2:
    skip;
  step3:
    skip;
""")
        assert len(blocks) == 3
        assert [b.label for b in blocks] == ["step1", "step2", "step3"]
        assert blocks[0].fall_through == "step2"
        assert blocks[1].fall_through == "step3"
        assert blocks[2].fall_through == "__done__"

    def test_while_loop(self):
        blocks = self._get_blocks("""
  loop:
    while (TRUE) {
      body:
        skip;
    };
  after:
    skip;
""")
        assert len(blocks) == 3
        labels = [b.label for b in blocks]
        assert labels == ["loop", "body", "after"]
        # loop is while entry
        assert blocks[0].while_label == "loop"
        assert blocks[0].while_guard is not None
        # body falls through to loop (back to while head)
        assert blocks[1].fall_through == "loop"
        # loop scope_exit is after
        assert blocks[0].scope_exit == "after"

    def test_if_with_labels(self):
        blocks = self._get_blocks("""
  check:
    if (msg = "yes") {
      inner1:
        skip;
    };
  after:
    skip;
""")
        labels = [b.label for b in blocks]
        assert "check" in labels
        assert "inner1" in labels
        assert "after" in labels
        check = next(b for b in blocks if b.label == "check")
        assert check.fall_through == "after"
        inner1 = next(b for b in blocks if b.label == "inner1")
        assert inner1.fall_through == "after"


# ===================================================================
# Integration tests: full parse of specific scenarios
# ===================================================================

class TestIntegration9E:
    """9E: Dining philosophers — 3 agents, 3 locks, no channels."""

    @pytest.fixture
    def result(self) -> ParseResult:
        tla, ir = _load_case("9E")
        return parse_pluscal(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_state_count(self, result: ParseResult):
        assert len(result.states) == 15

    def test_initial_states(self, result: ParseResult):
        assert result.initial_states == {
            "phil0": "p0_think",
            "phil1": "p1_think",
            "phil2": "p2_think",
        }

    def test_all_agents_assigned(self, result: ParseResult):
        agents = {s["agent"] for s in result.states}
        assert agents == {"phil0", "phil1", "phil2"}

    def test_phil0_state_chain(self, result: ParseResult):
        phil0 = {s["id"]: s for s in result.states if s["agent"] == "phil0"}
        assert set(phil0.keys()) == {
            "p0_think", "p0_get_first", "p0_get_second", "p0_eat", "p0_release",
        }
        assert phil0["p0_think"]["actions"][0]["next_state"] == "p0_get_first"
        assert phil0["p0_get_first"]["actions"][0]["next_state"] == "p0_get_second"
        assert phil0["p0_get_second"]["actions"][0]["next_state"] == "p0_eat"
        assert phil0["p0_eat"]["actions"][0]["next_state"] == "p0_release"

    def test_lock_acquire_pattern(self, result: ParseResult):
        phil0 = {s["id"]: s for s in result.states if s["agent"] == "phil0"}
        assert phil0["p0_get_first"]["actions"][0]["acquire"] == "fork0"
        assert phil0["p0_get_second"]["actions"][0]["acquire"] == "fork2"

    def test_lock_release_pattern(self, result: ParseResult):
        phil0 = {s["id"]: s for s in result.states if s["agent"] == "phil0"}
        release_action = phil0["p0_release"]["actions"][0]
        assert set(release_action["release"]) == {"fork0", "fork2"}


class TestIntegration10E:
    """10E: Parallel build — branching, channels, merged receive-dispatch."""

    @pytest.fixture
    def result(self) -> ParseResult:
        tla, ir = _load_case("10E")
        return parse_pluscal(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_state_count(self, result: ParseResult):
        assert len(result.states) == 19

    def test_initial_states(self, result: ParseResult):
        assert result.initial_states == {
            "builder_a": "ba_acq_core",
            "builder_b": "bb_acq_core",
            "integrator": "int_collect",
        }

    def test_nondeterministic_send(self, result: ParseResult):
        ba_notify = next(s for s in result.states if s["id"] == "ba_notify")
        assert len(ba_notify["actions"]) == 2
        labels = {a["send"]["label"] for a in ba_notify["actions"]}
        assert labels == {"types_updated", "types_stable"}

    def test_merged_receive_dispatch(self, result: ParseResult):
        assert not any(s["id"] == "bb_check" for s in result.states)
        assert "bb_check" in result.merged_state_ids
        bb_wait = next(s for s in result.states if s["id"] == "bb_wait_notify")
        assert len(bb_wait["actions"]) == 2
        targets = {a["next_state"] for a in bb_wait["actions"]}
        assert targets == {"bb_rebuild", "bb_done"}

    def test_terminal_state(self, result: ParseResult):
        int_link = next(s for s in result.states if s["id"] == "int_link")
        assert int_link["actions"] == []


class TestIntegration3E:
    """3E: Research writing — channels, either-or branching."""

    @pytest.fixture
    def result(self) -> ParseResult:
        tla, ir = _load_case("3E")
        return parse_pluscal(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_initial_states(self, result: ParseResult):
        ir = json.loads((IR_BASE / "3E" / "ir.json").read_text())
        ir_agents = {a["id"] for a in ir["agents"]}
        assert set(result.initial_states.keys()) == ir_agents


class TestIntegration4M:
    """4M: Code collaboration — while loops, either with labels, multi-action merge."""

    @pytest.fixture
    def result(self) -> ParseResult:
        tla, ir = _load_case("4M")
        return parse_pluscal(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_rv_recv_merged(self, result: ParseResult):
        """Reviewer receive state has 4 actions (2 channels × 2 labels)."""
        rv_recv = next(s for s in result.states if s["id"] == "rv_recv")
        assert len(rv_recv["actions"]) == 4
        for a in rv_recv["actions"]:
            assert "receive" in a
            assert "channel" in a["receive"]
            assert "label" in a["receive"]
        channels = {a["receive"]["channel"] for a in rv_recv["actions"]}
        assert len(channels) == 2

    def test_dev_wait_states_merged(self, result: ParseResult):
        for prefix in ("da", "db"):
            for suffix in ("wait_review", "wait_test", "wait_arch"):
                sid = f"{prefix}_{suffix}"
                state = next((s for s in result.states if s["id"] == sid), None)
                if state:
                    assert len(state["actions"]) == 2
                    for a in state["actions"]:
                        assert "receive" in a
                        assert "label" in a["receive"]


class TestIntegration7H:
    """7H: Document co-authoring — chained if-else-if with internal labels."""

    @pytest.fixture
    def result(self) -> ParseResult:
        tla, ir = _load_case("7H")
        return parse_pluscal(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_writer_rev_check_merged(self, result: ParseResult):
        """wa_rev_check (chained if-else-if) should be merged into wa_rev_wait."""
        assert "wa_rev_check" in result.merged_state_ids
        wa_rev_wait = next(s for s in result.states if s["id"] == "wa_rev_wait")
        assert len(wa_rev_wait["actions"]) == 3

    def test_minor_fix_states_present(self, result: ParseResult):
        """Minor fix/done states inside the else-if branch should be extracted."""
        state_ids = {s["id"] for s in result.states}
        for prefix in ("wa", "wb", "wc"):
            assert f"{prefix}_minor_fix" in state_ids
            assert f"{prefix}_minor_done" in state_ids


class TestIntegration8E:
    """8E: API system — nested either with labels inside if-else branch."""

    @pytest.fixture
    def result(self) -> ParseResult:
        tla, ir = _load_case("8E")
        return parse_pluscal(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_bd_wait_adjust_present(self, result: ParseResult):
        """bd_wait_adjust (label inside either-or inside if-else) should be extracted."""
        state_ids = {s["id"] for s in result.states}
        assert "bd_wait_adjust" in state_ids

    def test_bd_test_wait_has_3_actions(self, result: ParseResult):
        """bd_test_wait should have 3 actions after merge with bd_test_check."""
        bd_test_wait = next(s for s in result.states if s["id"] == "bd_test_wait")
        assert len(bd_test_wait["actions"]) == 3


class TestIntegration11M:
    """11M: Flexible manufacturing — counters, chained else-if."""

    @pytest.fixture
    def result(self) -> ParseResult:
        tla, ir = _load_case("11M")
        return parse_pluscal(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_all_worker_dispatches_merged(self, result: ParseResult):
        """All 12 worker dispatch states (*_check) should be merged."""
        for prefix in ("wa", "wb", "wc"):
            for suffix in ("j1_check", "j2_check", "s1_check", "s2_check"):
                sid = f"{prefix}_{suffix}"
                assert sid in result.merged_state_ids, f"{sid} should be merged"


# ===================================================================
# Inline label embedding tests
# ===================================================================


class TestInlineLabelEmbedding:
    """receive + if in the same label block should produce labeled receive."""

    def _parse_inline(self, body_code: str, ir_data: dict) -> ParseResult:
        tla = f"""---- MODULE T ----
(* --algorithm T {{
fair process (p_proc \\in {{P}})
variables msg = "";
{{
{body_code}
}}
}} *)
===="""
        return parse_pluscal(tla, ir_data)

    def test_inline_receive_if_label(self):
        """Single-block receive+if should embed label in receive dict."""
        ir = {
            "agents": [{"id": "p"}],
            "resources": [],
            "channels": [{"id": "ch_a", "from": "q", "to": "p", "labels": ["done", "more"]}],
        }
        result = self._parse_inline("""
  start:
    receive(ch_a, msg);
    if (msg = "done") { goto fin; };
  cont:
    skip;
  fin:
    skip;
""", ir)
        assert result.errors == []
        start = next(s for s in result.states if s["id"] == "start")
        # Should have 2 actions: one labeled "done" -> fin, one labeled "more" -> cont
        # ("more" is inferred by _infer_else_labels since it's the only missing label)
        assert len(start["actions"]) == 2
        done_actions = [a for a in start["actions"] if a.get("receive", {}).get("label") == "done"]
        assert len(done_actions) == 1
        assert done_actions[0]["next_state"] == "fin"
        more_actions = [a for a in start["actions"] if a.get("receive", {}).get("label") == "more"]
        assert len(more_actions) == 1
        assert more_actions[0]["next_state"] == "cont"

    def test_embed_inline_labels_direct(self):
        """Direct test of _embed_inline_labels on pre-built state dicts."""
        states = [
            {"id": "s1", "actions": [
                {"receive": {"channel": "ch"}, "_label": "approve", "next_state": "s2"},
                {"receive": {"channel": "ch"}, "next_state": "s3"},
            ]},
        ]
        count = _embed_inline_labels(states)
        assert count == 1
        assert states[0]["actions"][0]["receive"]["label"] == "approve"
        assert "label" not in states[0]["actions"][1]["receive"]

    def test_no_double_label(self):
        """Actions already labeled by merge pass should not be overwritten."""
        states = [
            {"id": "s1", "actions": [
                {"receive": {"channel": "ch", "label": "existing"}, "_label": "other", "next_state": "s2"},
            ]},
        ]
        count = _embed_inline_labels(states)
        assert count == 0
        assert states[0]["actions"][0]["receive"]["label"] == "existing"


# ===================================================================
# Cross-validation: pluscal_parser vs tla_parser for all IRs
# ===================================================================

def _normalize_action(action: dict) -> dict:
    """Normalize an action dict for comparison (sort inner arrays)."""
    a = copy.deepcopy(action)
    for key in ("acquire", "release", "increment"):
        if key in a and isinstance(a[key], list):
            a[key] = sorted(a[key])
    if "send" in a and isinstance(a["send"], list):
        a["send"] = sorted(a["send"], key=lambda x: json.dumps(x, sort_keys=True))
    if "receive" in a and isinstance(a["receive"], list):
        a["receive"] = sorted(a["receive"], key=lambda x: json.dumps(x, sort_keys=True))
    return a


def _normalize_state(state: dict) -> dict:
    """Normalize a state dict for comparison."""
    s = copy.deepcopy(state)
    s["actions"] = sorted(
        [_normalize_action(a) for a in s["actions"]],
        key=lambda x: json.dumps(x, sort_keys=True),
    )
    return s


@pytest.fixture(params=_available_cases(), scope="module")
def cross_case(request) -> tuple[str, ParseResult, ParseResult]:
    """For each available IR, parse with both parsers."""
    case_id = request.param
    tla, ir = _load_case(case_id)
    ref = parse_translated_tla(tla, ir)
    new = parse_pluscal(tla, ir)
    return case_id, ref, new


class TestCrossValidation:
    """Compare pluscal_parser output against tla_parser for all IRs."""

    def test_same_state_ids(self, cross_case):
        case_id, ref, new = cross_case
        ref_ids = {s["id"] for s in ref.states}
        new_ids = {s["id"] for s in new.states}
        assert new_ids == ref_ids, (
            f"{case_id}: state ID mismatch — "
            f"extra={new_ids - ref_ids}, missing={ref_ids - new_ids}"
        )

    def test_same_initial_states(self, cross_case):
        case_id, ref, new = cross_case
        assert new.initial_states == ref.initial_states, (
            f"{case_id}: initial_states mismatch"
        )

    def test_same_agent_assignments(self, cross_case):
        case_id, ref, new = cross_case
        ref_agents = {s["id"]: s["agent"] for s in ref.states}
        new_agents = {s["id"]: s["agent"] for s in new.states}
        assert new_agents == ref_agents, (
            f"{case_id}: agent assignment mismatch"
        )

    def test_same_actions_semantic(self, cross_case):
        """Actions should be semantically identical (ignoring ordering within arrays)."""
        case_id, ref, new = cross_case
        ref_map = {s["id"]: s for s in ref.states}
        new_map = {s["id"]: s for s in new.states}

        diffs = []
        for sid in sorted(ref_map.keys()):
            rn = _normalize_state(ref_map[sid])
            nn = _normalize_state(new_map[sid])
            if json.dumps(rn["actions"], sort_keys=True) != \
               json.dumps(nn["actions"], sort_keys=True):
                diffs.append(sid)

        assert diffs == [], (
            f"{case_id}: semantic diffs in states: {diffs}"
        )

    def test_same_merged_state_ids(self, cross_case):
        case_id, ref, new = cross_case
        assert new.merged_state_ids == ref.merged_state_ids, (
            f"{case_id}: merged_state_ids mismatch — "
            f"extra={new.merged_state_ids - ref.merged_state_ids}, "
            f"missing={ref.merged_state_ids - new.merged_state_ids}"
        )


# ===================================================================
# Batch validation: structural properties for all IRs
# ===================================================================

@pytest.fixture(params=_available_cases(), scope="module")
def case_result(request) -> tuple[str, ParseResult, dict]:
    """Parse each available IR with pluscal_parser."""
    case_id = request.param
    tla, ir = _load_case(case_id)
    result = parse_pluscal(tla, ir)
    return case_id, result, ir


class TestBatchValidation:
    """Structural validation applied to all available IRs."""

    def test_no_parse_errors(self, case_result):
        case_id, result, ir = case_result
        assert result.errors == [], f"Parse errors in {case_id}: {result.errors}"

    def test_action_targets_valid(self, case_result):
        case_id, result, ir = case_result
        state_ids = {s["id"] for s in result.states}
        for state in result.states:
            for action in state.get("actions", []):
                target = action.get("next_state")
                if target:
                    assert target in state_ids or target == "__done__", (
                        f"State '{state['id']}' targets unknown '{target}' in {case_id}"
                    )

    def test_resources_exist_in_ir(self, case_result):
        case_id, result, ir = case_result
        resource_ids = {r["id"] for r in ir.get("resources", [])}
        for state in result.states:
            for action in state.get("actions", []):
                for field in ("acquire", "release"):
                    val = action.get(field)
                    if val:
                        items = val if isinstance(val, list) else [val]
                        for item in items:
                            assert item in resource_ids, (
                                f"State '{state['id']}' uses unknown resource "
                                f"'{item}' in {case_id}"
                            )

    def test_channels_exist_in_ir(self, case_result):
        case_id, result, ir = case_result
        channel_ids = {c["id"] for c in ir.get("channels", [])}
        for state in result.states:
            for action in state.get("actions", []):
                for field in ("send", "receive"):
                    val = action.get(field)
                    if val:
                        items = val if isinstance(val, list) else [val]
                        for item in items:
                            if isinstance(item, dict) and "channel" in item:
                                assert item["channel"] in channel_ids, (
                                    f"State '{state['id']}' uses unknown channel "
                                    f"'{item['channel']}' in {case_id}"
                                )

    def test_initial_states_match_agents(self, case_result):
        case_id, result, ir = case_result
        ir_agent_ids = {a["id"] for a in ir.get("agents", [])}
        assert set(result.initial_states.keys()) == ir_agent_ids, (
            f"Initial states mismatch in {case_id}"
        )

    def test_every_agent_has_states(self, case_result):
        case_id, result, ir = case_result
        ir_agent_ids = {a["id"] for a in ir.get("agents", [])}
        agents_with_states = {s["agent"] for s in result.states}
        assert ir_agent_ids == agents_with_states, (
            f"Agent coverage mismatch in {case_id}"
        )

    def test_no_standalone_labels(self, case_result):
        """Labels should only appear inside receive dicts, never as standalone."""
        case_id, result, ir = case_result
        for state in result.states:
            for action in state.get("actions", []):
                assert "label" not in action, (
                    f"State '{state['id']}' has standalone label in {case_id}"
                )
                assert "_label" not in action, (
                    f"State '{state['id']}' has leaked _label in {case_id}"
                )
                assert "_cond_var" not in action, (
                    f"State '{state['id']}' has leaked _cond_var in {case_id}"
                )
                recv = action.get("receive")
                if isinstance(recv, dict):
                    assert "_recv_var" not in recv, (
                        f"State '{state['id']}' has leaked _recv_var in {case_id}"
                    )


# ===================================================================
# Lint: adjacent acquire → release without intermediate work
# ===================================================================

class TestLintAdjacentAcquireRelease:
    """Tests for lint_adjacent_acquire_release() on synthetic state data."""

    def test_adjacent_acquire_release_flagged(self):
        """acquire(X) → release(X), no intermediate → warning."""
        states = [
            {"id": "s_acq", "agent": "a", "actions": [
                {"acquire": "lock_x", "next_state": "s_rel"},
            ]},
            {"id": "s_rel", "agent": "a", "actions": [
                {"release": "lock_x", "next_state": "s_done"},
            ]},
            {"id": "s_done", "agent": "a", "actions": []},
        ]
        warnings = lint_adjacent_acquire_release(states)
        assert len(warnings) == 1
        assert "lock_x" in warnings[0]
        assert "s_acq" in warnings[0]
        assert "s_rel" in warnings[0]

    def test_receive_between_not_flagged(self):
        """acquire(X) → receive → release(X) → no warning."""
        states = [
            {"id": "s_acq", "agent": "a", "actions": [
                {"acquire": "lock_x", "next_state": "s_recv"},
            ]},
            {"id": "s_recv", "agent": "a", "actions": [
                {"receive": {"channel": "ch", "label": "msg"}, "next_state": "s_rel"},
            ]},
            {"id": "s_rel", "agent": "a", "actions": [
                {"release": "lock_x", "next_state": "s_done"},
            ]},
            {"id": "s_done", "agent": "a", "actions": []},
        ]
        warnings = lint_adjacent_acquire_release(states)
        assert len(warnings) == 0

    def test_send_between_not_flagged(self):
        """acquire(X) → send → release(X) → no warning."""
        states = [
            {"id": "s_acq", "agent": "a", "actions": [
                {"acquire": "lock_x", "next_state": "s_send"},
            ]},
            {"id": "s_send", "agent": "a", "actions": [
                {"send": {"channel": "ch", "label": "msg"}, "next_state": "s_rel"},
            ]},
            {"id": "s_rel", "agent": "a", "actions": [
                {"release": "lock_x", "next_state": "s_done"},
            ]},
            {"id": "s_done", "agent": "a", "actions": []},
        ]
        warnings = lint_adjacent_acquire_release(states)
        assert len(warnings) == 0

    def test_multiple_acquires_then_release_flagged(self):
        """acquire(A) → acquire(B) → release(B) → release(A), no work → warnings."""
        states = [
            {"id": "s_acq_a", "agent": "a", "actions": [
                {"acquire": "lock_a", "next_state": "s_acq_b"},
            ]},
            {"id": "s_acq_b", "agent": "a", "actions": [
                {"acquire": "lock_b", "next_state": "s_rel_b"},
            ]},
            {"id": "s_rel_b", "agent": "a", "actions": [
                {"release": "lock_b", "next_state": "s_rel_a"},
            ]},
            {"id": "s_rel_a", "agent": "a", "actions": [
                {"release": "lock_a", "next_state": "s_done"},
            ]},
            {"id": "s_done", "agent": "a", "actions": []},
        ]
        warnings = lint_adjacent_acquire_release(states)
        # s_acq_b → s_rel_b is adjacent acquire→release (lock_b)
        assert len(warnings) >= 1
        lock_b_warnings = [w for w in warnings if "lock_b" in w]
        assert len(lock_b_warnings) == 1

    def test_different_resources_not_flagged(self):
        """acquire(X) → release(Y) → no warning (different resources)."""
        states = [
            {"id": "s_acq", "agent": "a", "actions": [
                {"acquire": "lock_x", "next_state": "s_rel"},
            ]},
            {"id": "s_rel", "agent": "a", "actions": [
                {"release": "lock_y", "next_state": "s_done"},
            ]},
            {"id": "s_done", "agent": "a", "actions": []},
        ]
        warnings = lint_adjacent_acquire_release(states)
        assert len(warnings) == 0

    def test_acquire_list_format(self):
        """acquire as list: ["lock_x"] → release ["lock_x"] → warning."""
        states = [
            {"id": "s_acq", "agent": "a", "actions": [
                {"acquire": ["lock_x"], "next_state": "s_rel"},
            ]},
            {"id": "s_rel", "agent": "a", "actions": [
                {"release": ["lock_x"], "next_state": "s_done"},
            ]},
            {"id": "s_done", "agent": "a", "actions": []},
        ]
        warnings = lint_adjacent_acquire_release(states)
        assert len(warnings) == 1

    def test_guard_between_not_flagged(self):
        """acquire(X) → [guard + release(X)] → no warning (guard = work)."""
        states = [
            {"id": "s_acq", "agent": "a", "actions": [
                {"acquire": "lock_x", "next_state": "s_check"},
            ]},
            {"id": "s_check", "agent": "a", "actions": [
                {"release": "lock_x", "guard": {"var": "count", "op": "<", "value": 3}, "next_state": "s_done"},
            ]},
            {"id": "s_done", "agent": "a", "actions": []},
        ]
        warnings = lint_adjacent_acquire_release(states)
        assert len(warnings) == 0
