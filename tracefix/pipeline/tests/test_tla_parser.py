"""Tests for tla_parser — TLA+ translated spec → IR v3 states extraction.

Structured as:
  1. Unit tests: individual parsing functions
  2. Integration tests: full parse of specific scenarios (9E, 10E, 3E)
  3. Batch validation: all 27 IR directories
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tracefix.pipeline.pipeline.tla_parser import (
    IRMetadata,
    ParseResult,
    build_ir_metadata,
    extract_translation_block,
    parse_init,
    parse_process_aggregations,
    parse_translated_tla,
    split_operators,
    parse_operator,
    _extract_loop_guard,
    _extract_increments,
    _parse_local_var_inits,
)

IR_BASE = Path(__file__).parent / "fixtures"


def _load_case(case_id: str) -> tuple[str, dict]:
    """Load a test case's TLA+ content and IR data."""
    case_dir = IR_BASE / case_id
    tla_content = (case_dir / "Protocol_translated.tla").read_text()
    ir_data = json.loads((case_dir / "ir.json").read_text())
    return tla_content, ir_data


# ===================================================================
# Unit tests: extract_translation_block
# ===================================================================

class TestExtractTranslationBlock:
    def test_extracts_block(self):
        content = (
            "stuff before\n"
            "\\* BEGIN TRANSLATION (chksum...)\n"
            "VARIABLES pc\n"
            "Init == TRUE\n"
            "\\* END TRANSLATION \n"
            "stuff after\n"
        )
        block = extract_translation_block(content)
        assert "VARIABLES pc" in block
        assert "Init == TRUE" in block
        assert "stuff before" not in block
        assert "stuff after" not in block

    def test_raises_on_missing_block(self):
        with pytest.raises(ValueError, match="No BEGIN/END TRANSLATION"):
            extract_translation_block("no translation here")

    def test_real_file_9e(self):
        tla, _ = _load_case("9E")
        block = extract_translation_block(tla)
        assert "ProcSet" in block
        assert "Init ==" in block
        assert "phil0_proc(self)" in block


# ===================================================================
# Unit tests: parse_init
# ===================================================================

class TestParseInit:
    def test_single_agent(self):
        block = (
            '/\\ pc = [self \\in ProcSet |-> CASE self \\in {Phil0} -> "p0_think"]\n'
        )
        result = parse_init(block)
        assert result == {"Phil0": "p0_think"}

    def test_multiple_agents(self):
        block = (
            '/\\ pc = [self \\in ProcSet |-> CASE self \\in {Phil0} -> "p0_think"\n'
            '                                    [] self \\in {Phil1} -> "p1_think"\n'
            '                                    [] self \\in {Phil2} -> "p2_think"]\n'
        )
        result = parse_init(block)
        assert result == {
            "Phil0": "p0_think",
            "Phil1": "p1_think",
            "Phil2": "p2_think",
        }

    def test_real_file_10e(self):
        tla, _ = _load_case("10E")
        block = extract_translation_block(tla)
        init = parse_init(block)
        assert init == {
            "Builder_a": "ba_acq_core",
            "Builder_b": "bb_acq_core",
            "Integrator": "int_collect",
        }


# ===================================================================
# Unit tests: parse_process_aggregations
# ===================================================================

class TestParseProcessAggregations:
    def test_real_file_9e(self):
        tla, _ = _load_case("9E")
        block = extract_translation_block(tla)
        aggs = parse_process_aggregations(block)
        assert "phil0_proc" in aggs
        assert "phil1_proc" in aggs
        assert "phil2_proc" in aggs
        assert "p0_think" in aggs["phil0_proc"]
        assert "p0_release" in aggs["phil0_proc"]

    def test_real_file_10e(self):
        tla, _ = _load_case("10E")
        block = extract_translation_block(tla)
        aggs = parse_process_aggregations(block)
        assert set(aggs.keys()) == {"builder_a_proc", "builder_b_proc", "integrator_proc"}
        assert "ba_notify" in aggs["builder_a_proc"]
        assert "bb_check" in aggs["builder_b_proc"]
        assert "int_recv" in aggs["integrator_proc"]


# ===================================================================
# Unit tests: split_operators
# ===================================================================

class TestSplitOperators:
    def test_real_file_9e(self):
        tla, _ = _load_case("9E")
        block = extract_translation_block(tla)
        ops = split_operators(block)
        names = [name for name, _ in ops]
        # Should include individual labels and aggregations
        assert "p0_think" in names
        assert "p0_release" in names
        assert "phil0_proc" in names
        # Should NOT include non-self operators
        assert "Terminating" not in names

    def test_body_does_not_include_next_operator(self):
        tla, _ = _load_case("9E")
        block = extract_translation_block(tla)
        ops = split_operators(block)
        op_dict = dict(ops)
        # p0_think body should not contain p0_get_first definition
        assert "p0_get_first(self) ==" not in op_dict["p0_think"]


# ===================================================================
# Unit tests: parse_operator
# ===================================================================

class TestParseOperator:
    def _get_operator(self, case_id: str, op_name: str) -> tuple[str, str, IRMetadata]:
        tla, ir = _load_case(case_id)
        block = extract_translation_block(tla)
        meta = build_ir_metadata(ir)
        ops = dict(split_operators(block))
        return op_name, ops[op_name], meta

    def test_simple_skip(self):
        """p0_think: /\\ TRUE, pc' -> next."""
        name, body, meta = self._get_operator("9E", "p0_think")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 1
        assert actions[0].target == "p0_get_first"
        assert actions[0].acquires == []
        assert actions[0].releases == []

    def test_lock_acquire(self):
        """p0_get_first: fork0 = FREE, fork0' = self."""
        name, body, meta = self._get_operator("9E", "p0_get_first")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 1
        assert actions[0].target == "p0_get_second"
        assert actions[0].acquires == ["fork0"]

    def test_lock_release(self):
        """ba_rel_core: core_lib' = FREE."""
        name, body, meta = self._get_operator("10E", "ba_rel_core")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 1
        assert actions[0].target == "ba_acq_types"
        assert actions[0].releases == ["core_lib"]

    def test_multi_lock_release(self):
        """p0_release: releases fork2 and fork0, transitions to Done."""
        name, body, meta = self._get_operator("9E", "p0_release")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 1
        assert actions[0].target == "__done__"
        assert set(actions[0].releases) == {"fork0", "fork2"}

    def test_channel_send(self):
        """ba_done: sends 'done' to a_to_integrator."""
        name, body, meta = self._get_operator("10E", "ba_done")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 1
        assert actions[0].sends == [{"channel": "a_to_integrator", "label": "done"}]

    def test_channel_receive(self):
        """bb_wait_notify: receives from a_to_b."""
        name, body, meta = self._get_operator("10E", "bb_wait_notify")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 1
        assert actions[0].receives[0]["channel"] == "a_to_b"
        # _recv_var is an internal field extracted for merge variable-match check
        assert actions[0].receives[0].get("_recv_var") == "msg_b"

    def test_if_then_else(self):
        """bb_check: IF msg = types_updated THEN rebuild ELSE done."""
        name, body, meta = self._get_operator("10E", "bb_check")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 2
        targets = {a.target for a in actions}
        assert targets == {"bb_rebuild", "bb_done"}
        # THEN branch has label from IF condition
        then_action = next(a for a in actions if a.target == "bb_rebuild")
        assert then_action.label == "types_updated"
        # ELSE branch has no label (default case)
        else_action = next(a for a in actions if a.target == "bb_done")
        assert else_action.label is None

    def test_nondeterministic_choice_shared_target(self):
        """ba_notify: \\/ send types_updated \\/ send types_stable, both -> ba_done."""
        name, body, meta = self._get_operator("10E", "ba_notify")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 2
        assert all(a.target == "ba_done" for a in actions)
        labels = {a.sends[0]["label"] for a in actions}
        assert labels == {"types_updated", "types_stable"}

    def test_nondeterministic_choice_per_branch_target(self):
        """e_decide: 4 branches with different targets."""
        name, body, meta = self._get_operator("3E", "e_decide")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 4
        targets = {a.target for a in actions}
        assert "e_done" in targets
        assert "e_rewaitA" in targets
        assert "e_rewaitB" in targets
        assert "e_collect" in targets

    def test_nondeterministic_receive(self):
        """int_recv: receive from a_to_integrator OR b_to_integrator."""
        name, body, meta = self._get_operator("10E", "int_recv")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 2
        channels = {a.receives[0]["channel"] for a in actions}
        assert channels == {"a_to_integrator", "b_to_integrator"}

    def test_terminal_with_true(self):
        """int_link: /\\ TRUE, pc' = Done -> terminal."""
        name, body, meta = self._get_operator("10E", "int_link")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 1
        assert actions[0].target == "__done__"
        assert actions[0].acquires == []
        assert actions[0].releases == []
        assert actions[0].sends == []

    def test_counter_acquire(self):
        """wa_j1_tool: tool_cabinet > 0, tool_cabinet' = tool_cabinet - 1."""
        name, body, meta = self._get_operator("11M", "wa_j1_tool")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 1
        assert "tool_cabinet" in actions[0].acquires

    def test_counter_release(self):
        """wa_j1_work: tool_cabinet' = tool_cabinet + 1."""
        name, body, meta = self._get_operator("11M", "wa_j1_work")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 1
        assert "tool_cabinet" in actions[0].releases

    def test_release_plus_send(self):
        """ra_release_ref: releases ref_lock AND sends submit."""
        name, body, meta = self._get_operator("3E", "ra_release_ref")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 1
        assert "ref_lock" in actions[0].releases
        assert actions[0].sends == [{"channel": "resA_to_editor", "label": "submit"}]

    def test_chained_if_else_if(self):
        """wc_rev_check: IF msg = major THEN ... ELSE IF msg = minor THEN ... ELSE ..."""
        name, body, meta = self._get_operator("7H", "wc_rev_check")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 3
        targets = {a.target for a in actions}
        assert targets == {"wc_major_fix", "wc_minor_fix", "wc_eic_wait"}
        # First branch: IF msg_ = "major"
        major_action = next(a for a in actions if a.target == "wc_major_fix")
        assert major_action.label == "major"
        # Second branch: ELSE IF msg_ = "minor"
        minor_action = next(a for a in actions if a.target == "wc_minor_fix")
        assert minor_action.label == "minor"
        # Default ELSE branch: no label
        default_action = next(a for a in actions if a.target == "wc_eic_wait")
        assert default_action.label is None

    def test_if_label_for_message_equality(self):
        """ra_check (3E): IF msg_ = accept THEN done ELSE write."""
        name, body, meta = self._get_operator("3E", "ra_check")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 2
        then_action = next(a for a in actions if a.target == "ra_done")
        assert then_action.label == "accept"
        else_action = next(a for a in actions if a.target == "ra_write")
        assert else_action.label is None

    def test_if_no_label_for_boolean(self):
        r"""rv_loop (6E): IF ~doneA \/ ~doneB -> no message label extracted."""
        name, body, meta = self._get_operator("6E", "rv_loop")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 2
        # Boolean negation conditions should not extract labels
        for a in actions:
            assert a.label is None

    def test_nested_if_multiline_3m(self):
        """ed_dispatch (3M): nested IF with multi-line branches produces 3 actions."""
        name, body, meta = self._get_operator("3M", "ed_dispatch")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 3
        # All three branches go to same target
        assert all(a.target == "ed_collect" for a in actions)
        # Labels: passedA, passedB, and default (None)
        labels = {a.label for a in actions}
        assert labels == {"passedA", "passedB", None}

    def test_nested_if_multiline_11h(self):
        """in_pass (11H): 4-deep nested IF produces 4 actions."""
        name, body, meta = self._get_operator("11H", "in_pass")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 4
        # All branches go to same target
        assert all(a.target == "in_loop" for a in actions)
        # Labels: A, B, C, and default (None)
        labels = {a.label for a in actions}
        assert labels == {"A", "B", "C", None}

    def test_nested_if_multiline_11m(self):
        """di_check (11M): 4-deep nested IF produces 4 actions."""
        name, body, meta = self._get_operator("11M", "di_check")
        actions = parse_operator(name, body, meta)
        assert len(actions) == 4
        # Labels: all_done, fail_A, fail_B, and default (None)
        labels = {a.label for a in actions}
        assert labels == {"all_done", "fail_A", "fail_B", None}

    def test_skips_aggregation_operator(self):
        """Process aggregation operators have no pc guard -> returns []."""
        tla, ir = _load_case("9E")
        block = extract_translation_block(tla)
        meta = build_ir_metadata(ir)
        ops = dict(split_operators(block))
        actions = parse_operator("phil0_proc", ops["phil0_proc"], meta)
        assert actions == []


# ===================================================================
# Unit tests: build_ir_metadata
# ===================================================================

class TestBuildIRMetadata:
    def test_locks_and_channels(self):
        ir = {
            "resources": [
                {"id": "core_lib", "type": "Lock"},
                {"id": "shared_types", "type": "Lock"},
            ],
            "channels": [
                {"id": "a_to_b", "from": "a", "to": "b", "labels": ["msg"]},
            ],
            "agents": [{"id": "a"}, {"id": "b"}],
        }
        meta = build_ir_metadata(ir)
        assert meta.lock_vars == {"core_lib": "core_lib", "shared_types": "shared_types"}
        assert meta.channel_vars == {"a_to_b": "a_to_b"}
        assert meta.counter_vars == {}

    def test_counter(self):
        ir = {
            "resources": [{"id": "tool_cabinet", "type": "Counter", "config": {"initial": 2}}],
            "channels": [],
            "agents": [],
        }
        meta = build_ir_metadata(ir)
        assert meta.counter_vars == {"tool_cabinet": "tool_cabinet"}
        assert meta.lock_vars == {}


# ===================================================================
# Integration tests: full parse of specific scenarios
# ===================================================================

class TestIntegration9E:
    """9E: Dining philosophers — 3 agents, 3 locks, no channels."""

    @pytest.fixture
    def result(self) -> ParseResult:
        tla, ir = _load_case("9E")
        return parse_translated_tla(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_state_count(self, result: ParseResult):
        assert len(result.states) == 15  # 5 states × 3 philosophers

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
        assert set(phil0.keys()) == {"p0_think", "p0_get_first", "p0_get_second", "p0_eat", "p0_release"}

        # Check transitions form a chain
        assert phil0["p0_think"]["actions"][0]["next_state"] == "p0_get_first"
        assert phil0["p0_get_first"]["actions"][0]["next_state"] == "p0_get_second"
        assert phil0["p0_get_second"]["actions"][0]["next_state"] == "p0_eat"
        assert phil0["p0_eat"]["actions"][0]["next_state"] == "p0_release"

    def test_lock_acquire_pattern(self, result: ParseResult):
        """Philosophers acquire forks in the correct order."""
        phil0 = {s["id"]: s for s in result.states if s["agent"] == "phil0"}
        assert phil0["p0_get_first"]["actions"][0]["acquire"] == "fork0"
        assert phil0["p0_get_second"]["actions"][0]["acquire"] == "fork2"

    def test_lock_release_pattern(self, result: ParseResult):
        """Release state releases both forks."""
        phil0 = {s["id"]: s for s in result.states if s["agent"] == "phil0"}
        release_action = phil0["p0_release"]["actions"][0]
        assert set(release_action["release"]) == {"fork0", "fork2"}


class TestIntegration10E:
    """10E: Parallel build — 3 agents, 2 locks, 3 channels, branching."""

    @pytest.fixture
    def result(self) -> ParseResult:
        tla, ir = _load_case("10E")
        return parse_translated_tla(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_state_count(self, result: ParseResult):
        assert len(result.states) == 19  # bb_check merged into bb_wait_notify

    def test_initial_states(self, result: ParseResult):
        assert result.initial_states == {
            "builder_a": "ba_acq_core",
            "builder_b": "bb_acq_core",
            "integrator": "int_collect",
        }

    def test_nondeterministic_send(self, result: ParseResult):
        """ba_notify has 2 nondeterministic send options."""
        ba_notify = next(s for s in result.states if s["id"] == "ba_notify")
        assert len(ba_notify["actions"]) == 2
        labels = {a["send"]["label"] for a in ba_notify["actions"]}
        assert labels == {"types_updated", "types_stable"}

    def test_merged_receive_dispatch(self, result: ParseResult):
        """bb_wait_notify merges bb_check: receive+label in same action."""
        # bb_check should be gone
        assert not any(s["id"] == "bb_check" for s in result.states)
        assert "bb_check" in result.merged_state_ids
        # bb_wait_notify now has 2 actions with receive+label
        bb_wait = next(s for s in result.states if s["id"] == "bb_wait_notify")
        assert len(bb_wait["actions"]) == 2
        targets = {a["next_state"] for a in bb_wait["actions"]}
        assert targets == {"bb_rebuild", "bb_done"}
        # THEN branch: receive with label
        rebuild_action = next(a for a in bb_wait["actions"] if a["next_state"] == "bb_rebuild")
        assert rebuild_action["receive"] == {"channel": "a_to_b", "label": "types_updated"}
        # ELSE branch: label inferred from IR channel labels by elimination
        done_action = next(a for a in bb_wait["actions"] if a["next_state"] == "bb_done")
        assert done_action["receive"] == {"channel": "a_to_b", "label": "types_stable"}

    def test_nondeterministic_receive(self, result: ParseResult):
        """int_recv nondeterministically receives from 2 channels."""
        int_recv = next(s for s in result.states if s["id"] == "int_recv")
        assert len(int_recv["actions"]) == 2
        channels = {a["receive"]["channel"] for a in int_recv["actions"]}
        assert channels == {"a_to_integrator", "b_to_integrator"}

    def test_terminal_state(self, result: ParseResult):
        """int_link is a terminal state."""
        int_link = next(s for s in result.states if s["id"] == "int_link")
        assert int_link["actions"] == []

    def test_send_before_done(self, result: ParseResult):
        """ba_done sends to a_to_integrator then transitions to Done."""
        ba_done = next(s for s in result.states if s["id"] == "ba_done")
        assert len(ba_done["actions"]) == 1
        a = ba_done["actions"][0]
        assert a["send"] == {"channel": "a_to_integrator", "label": "done"}


class TestIntegration3E:
    """3E: Research writing — 3 agents, 2 locks, 4 channels, 4-way nondeterminism."""

    @pytest.fixture
    def result(self) -> ParseResult:
        tla, ir = _load_case("3E")
        return parse_translated_tla(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_state_count(self, result: ParseResult):
        assert len(result.states) == 23  # ra_check + rb_check merged away

    def test_four_way_nondeterminism(self, result: ParseResult):
        """e_decide has 4 nondeterministic branches."""
        e_decide = next(s for s in result.states if s["id"] == "e_decide")
        assert len(e_decide["actions"]) == 4
        targets = {a["next_state"] for a in e_decide["actions"]}
        assert targets == {"e_done", "e_rewaitA", "e_rewaitB", "e_collect"}

    def test_e_decide_all_release_lock(self, result: ParseResult):
        """All e_decide branches release doc_lock."""
        e_decide = next(s for s in result.states if s["id"] == "e_decide")
        for action in e_decide["actions"]:
            assert action["release"] == "doc_lock"

    def test_release_plus_send(self, result: ParseResult):
        """ra_release_ref releases lock and sends message."""
        ra_rel = next(s for s in result.states if s["id"] == "ra_release_ref")
        assert len(ra_rel["actions"]) == 1
        a = ra_rel["actions"][0]
        assert a["release"] == "ref_lock"
        assert a["send"] == {"channel": "resA_to_editor", "label": "submit"}

    def test_loop_back(self, result: ParseResult):
        """ra_wait (merged from ra_check) can loop back to ra_write (revision loop)."""
        ra_wait = next(s for s in result.states if s["id"] == "ra_wait")
        targets = {a["next_state"] for a in ra_wait["actions"]}
        assert "ra_write" in targets


class TestIntegration7H:
    """7H: Large document — 7 agents, 5 locks, 24 channels, chained IF-ELSE-IF."""

    @pytest.fixture
    def result(self) -> ParseResult:
        tla, ir = _load_case("7H")
        return parse_translated_tla(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_chained_if_labels(self, result: ParseResult):
        """wc_rev_check merged into wc_rev_wait: 3-way branch with receive+label."""
        assert not any(s["id"] == "wc_rev_check" for s in result.states)
        wc_wait = next(s for s in result.states if s["id"] == "wc_rev_wait")
        assert len(wc_wait["actions"]) == 3
        targets = {a["next_state"] for a in wc_wait["actions"]}
        assert targets == {"wc_major_fix", "wc_minor_fix", "wc_eic_wait"}
        # Labels are inside receive dicts
        major = next(a for a in wc_wait["actions"] if a["next_state"] == "wc_major_fix")
        assert major["receive"] == {"channel": "rev_to_wC", "label": "major"}
        minor = next(a for a in wc_wait["actions"] if a["next_state"] == "wc_minor_fix")
        assert minor["receive"] == {"channel": "rev_to_wC", "label": "minor"}
        # ELSE branch: label inferred from IR channel labels by elimination
        default = next(a for a in wc_wait["actions"] if a["next_state"] == "wc_eic_wait")
        assert default["receive"] == {"channel": "rev_to_wC", "label": "ok"}

    def test_all_writers_have_merged_rev_wait(self, result: ParseResult):
        """All 3 writers (wA, wB, wC) have merged rev_wait with receive+label."""
        for prefix in ("wa", "wb", "wc"):
            # rev_check should be merged away
            assert not any(s["id"] == f"{prefix}_rev_check" for s in result.states)
            # rev_wait should have the merged actions
            rev_wait = next(s for s in result.states if s["id"] == f"{prefix}_rev_wait")
            assert len(rev_wait["actions"]) == 3
            # Labels are inside receive dicts
            recv_labels = [a["receive"].get("label") for a in rev_wait["actions"]]
            assert "major" in recv_labels
            assert "minor" in recv_labels


class TestIntegration11M:
    """11M: Manufacturing — 5 agents, 3 locks + 1 counter, 10 channels."""

    @pytest.fixture
    def result(self) -> ParseResult:
        tla, ir = _load_case("11M")
        return parse_translated_tla(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_counter_acquire_and_release(self, result: ParseResult):
        """Workers acquire and release tool_cabinet counter."""
        wa_j1_tool = next(s for s in result.states if s["id"] == "wa_j1_tool")
        assert wa_j1_tool["actions"][0]["acquire"] == "tool_cabinet"

        wa_j1_work = next(s for s in result.states if s["id"] == "wa_j1_work")
        a = wa_j1_work["actions"][0]
        assert "tool_cabinet" in (a["release"] if isinstance(a["release"], list) else [a["release"]])


# ===================================================================
# Batch validation: all 27 IR directories
# ===================================================================

# ===================================================================
# Unit tests: _extract_loop_guard
# ===================================================================

class TestExtractLoopGuard:
    def test_less_than(self):
        assert _extract_loop_guard("passed[self] < 8") == {
            "var": "passed", "op": "<", "value": 8,
        }

    def test_less_than_equal(self):
        assert _extract_loop_guard("count[self] <= 3") == {
            "var": "count", "op": "<=", "value": 3,
        }

    def test_greater_than(self):
        assert _extract_loop_guard("x[self] > 0") == {
            "var": "x", "op": ">", "value": 0,
        }

    def test_equality(self):
        assert _extract_loop_guard("n[self] = 5") == {
            "var": "n", "op": "=", "value": 5,
        }

    def test_reverse_form(self):
        """Reverse form like ``2 > var[self]`` should flip to ``var < 2``."""
        result = _extract_loop_guard("2 > cnt[self]")
        assert result == {"var": "cnt", "op": "<", "value": 2}

    def test_returns_none_for_string_equality(self):
        """Should not match message label conditions."""
        assert _extract_loop_guard('msg_[self] = "approved"') is None

    def test_returns_none_for_no_match(self):
        assert _extract_loop_guard("TRUE") is None
        assert _extract_loop_guard("flag[self]") is None


# ===================================================================
# Unit tests: _extract_increments
# ===================================================================

class TestExtractIncrements:
    def test_simple_increment(self):
        text = r"passed' = [passed EXCEPT ![self] = passed[self] + 1]"
        meta = IRMetadata()
        assert _extract_increments(text, meta) == ["passed"]

    def test_excludes_ir_counters(self):
        text = r"tool_supply' = [tool_supply EXCEPT ![self] = tool_supply[self] + 1]"
        meta = IRMetadata(counter_vars={"tool_supply": "tool_supply"})
        assert _extract_increments(text, meta) == []

    def test_excludes_ir_locks(self):
        text = r"mylock' = [mylock EXCEPT ![self] = mylock[self] + 1]"
        meta = IRMetadata(lock_vars={"mylock": "mylock"})
        assert _extract_increments(text, meta) == []

    def test_multiple_increments(self):
        text = (
            r"a' = [a EXCEPT ![self] = a[self] + 1]"
            "\n"
            r"b' = [b EXCEPT ![self] = b[self] + 1]"
        )
        meta = IRMetadata()
        assert _extract_increments(text, meta) == ["a", "b"]

    def test_no_match(self):
        text = r"pc' = [pc EXCEPT ![self] = ""Done""]"
        meta = IRMetadata()
        assert _extract_increments(text, meta) == []


# ===================================================================
# Unit tests: _parse_local_var_inits
# ===================================================================

class TestParseLocalVarInits:
    def test_integer_init(self):
        block = r'/\ count = [self \in {Supervisor} |-> 0]'
        result = _parse_local_var_inits(block)
        assert result == {
            "count": {"initial": 0, "process_constant": "Supervisor"},
        }

    def test_string_init(self):
        block = r'/\ msg_ = [self \in {Architect} |-> ""]'
        result = _parse_local_var_inits(block)
        assert result == {
            "msg_": {"initial": "", "process_constant": "Architect"},
        }

    def test_boolean_init(self):
        block = r'/\ done = [self \in {Worker} |-> FALSE]'
        result = _parse_local_var_inits(block)
        assert result == {
            "done": {"initial": "FALSE", "process_constant": "Worker"},
        }

    def test_multiple_vars(self):
        block = (
            r'/\ passed = [self \in {Inspector} |-> 0]' "\n"
            r'/\ count = [self \in {Packager} |-> 0]' "\n"
            r'/\ msg = [self \in {Inspector} |-> ""]'
        )
        result = _parse_local_var_inits(block)
        assert "passed" in result
        assert "count" in result
        assert "msg" in result
        assert result["passed"]["initial"] == 0
        assert result["count"]["initial"] == 0

    def test_real_file_11e(self):
        tla, _ = _load_case("11E")
        block = extract_translation_block(tla)
        result = _parse_local_var_inits(block)
        assert "count" in result
        assert result["count"] == {"initial": 0, "process_constant": "Supervisor"}


# ===================================================================
# Integration: while-loop extraction (11H)
# ===================================================================

class TestWhileLoopIntegration11H:
    @pytest.fixture(scope="class")
    def result(self) -> ParseResult:
        tla, ir = _load_case("11H")
        return parse_translated_tla(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_in_loop_has_guard(self, result: ParseResult):
        """in_loop state should have a guarded THEN action (passed < 8)."""
        state = next(s for s in result.states if s["id"] == "in_loop")
        actions = state["actions"]
        assert len(actions) == 2
        guarded = [a for a in actions if a.get("guard")]
        assert len(guarded) == 1
        g = guarded[0]["guard"]
        assert g["var"] == "passed"
        assert g["op"] == "<"
        assert g["value"] == 8
        assert guarded[0]["next_state"] == "in_recv"

    def test_in_loop_else_no_guard(self, result: ParseResult):
        """The ELSE branch of in_loop should not have a guard."""
        state = next(s for s in result.states if s["id"] == "in_loop")
        actions = state["actions"]
        unguarded = [a for a in actions if not a.get("guard")]
        assert len(unguarded) == 1
        assert unguarded[0]["next_state"] == "in_signal"

    def test_in_pass_has_increment(self, result: ParseResult):
        """in_pass state actions should have increment on 'passed'."""
        state = next(s for s in result.states if s["id"] == "in_pass")
        # All actions in this state should increment 'passed'
        for action in state["actions"]:
            assert action.get("increment") == "passed", (
                f"Action targeting {action.get('next_state')} missing increment"
            )

    def test_pk_loop_has_guard(self, result: ParseResult):
        """pk_loop state should have guard count < 8."""
        state = next(s for s in result.states if s["id"] == "pk_loop")
        guarded = [a for a in state["actions"] if a.get("guard")]
        assert len(guarded) == 1
        assert guarded[0]["guard"]["var"] == "count"
        assert guarded[0]["guard"]["value"] == 8

    def test_local_variables_populated(self, result: ParseResult):
        """local_variables should contain passed and count."""
        assert "passed" in result.local_variables
        assert result.local_variables["passed"]["initial"] == 0
        assert result.local_variables["passed"]["agent"] == "inspector"
        assert "count" in result.local_variables
        assert result.local_variables["count"]["initial"] == 0
        assert result.local_variables["count"]["agent"] == "packager"


# ===================================================================
# Integration: while-loop extraction (11E)
# ===================================================================

class TestWhileLoopIntegration11E:
    @pytest.fixture(scope="class")
    def result(self) -> ParseResult:
        tla, ir = _load_case("11E")
        return parse_translated_tla(tla, ir)

    def test_sup_collect_has_guard(self, result: ParseResult):
        """sup_collect should have guard count < 4."""
        state = next(s for s in result.states if s["id"] == "sup_collect")
        guarded = [a for a in state["actions"] if a.get("guard")]
        assert len(guarded) == 1
        g = guarded[0]["guard"]
        assert g == {"var": "count", "op": "<", "value": 4}

    def test_local_variables(self, result: ParseResult):
        assert "count" in result.local_variables
        assert result.local_variables["count"]["initial"] == 0
        assert result.local_variables["count"]["agent"] == "supervisor"


# ===================================================================
# Batch: guard/increment backward compatibility
# ===================================================================

def _guard_compat_case_ids() -> list[str]:
    """Return all case IDs (duplicate of _all_case_ids, defined before it)."""
    _root = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
    base = _root / "IRs"
    if not base.exists():
        return []
    ids = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / "ir.json").exists() and (d / "Protocol_translated.tla").exists():
            ids.append(d.name)
    return ids


@pytest.mark.parametrize("case_id", _guard_compat_case_ids())
class TestBatchGuardCompat:
    """Ensure guard/increment fields don't break any existing task."""

    def test_no_errors_with_new_fields(self, case_id: str):
        tla, ir = _load_case(case_id)
        result = parse_translated_tla(tla, ir)
        assert result.errors == [], f"Parse errors in {case_id}: {result.errors}"

    def test_local_variables_only_for_guard_vars(self, case_id: str):
        """local_variables should only contain vars used as guards or increments."""
        tla, ir = _load_case(case_id)
        result = parse_translated_tla(tla, ir)
        # Collect all guard/increment var names from states
        referenced = set()
        for state in result.states:
            for action in state.get("actions", []):
                g = action.get("guard")
                if g:
                    referenced.add(g["var"])
                inc = action.get("increment")
                if inc:
                    items = inc if isinstance(inc, list) else [inc]
                    referenced.update(items)
        assert set(result.local_variables.keys()) <= referenced, (
            f"local_variables has unreferenced vars in {case_id}"
        )


def _all_case_ids() -> list[str]:
    """Return all case IDs that have both ir.json and Protocol_translated.tla."""
    if not IR_BASE.exists():
        return []
    ids = []
    for d in sorted(IR_BASE.iterdir()):
        if d.is_dir() and (d / "ir.json").exists() and (d / "Protocol_translated.tla").exists():
            ids.append(d.name)
    return ids


ALL_CASES = _all_case_ids()


@pytest.mark.parametrize("case_id", ALL_CASES)
class TestBatchValidation:
    """Batch validation across all IR directories."""

    def test_no_parse_errors(self, case_id: str):
        tla, ir = _load_case(case_id)
        result = parse_translated_tla(tla, ir)
        assert result.errors == [], f"Parse errors in {case_id}: {result.errors}"

    def test_all_labels_have_states(self, case_id: str):
        """Every label in process aggregations should have a state or be merged away."""
        tla, ir = _load_case(case_id)
        block = extract_translation_block(tla)
        aggs = parse_process_aggregations(block)
        result = parse_translated_tla(tla, ir)

        state_ids = {s["id"] for s in result.states}
        covered = state_ids | result.merged_state_ids
        for proc_name, labels in aggs.items():
            for label in labels:
                assert label in covered, (
                    f"Label '{label}' from {proc_name} has no state in {case_id}"
                )

    def test_action_targets_valid(self, case_id: str):
        """Every action target should point to a known state or __done__."""
        tla, ir = _load_case(case_id)
        result = parse_translated_tla(tla, ir)

        state_ids = {s["id"] for s in result.states}
        for state in result.states:
            for action in state.get("actions", []):
                target = action.get("next_state")
                if target:
                    assert target in state_ids or target == "__done__", (
                        f"State '{state['id']}' targets unknown '{target}' in {case_id}"
                    )

    def test_resources_exist_in_ir(self, case_id: str):
        """Every acquire/release resource must exist in ir.json."""
        tla, ir = _load_case(case_id)
        result = parse_translated_tla(tla, ir)

        resource_ids = {r["id"] for r in ir.get("resources", [])}
        for state in result.states:
            for action in state.get("actions", []):
                for field in ("acquire", "release"):
                    val = action.get(field)
                    if val:
                        items = val if isinstance(val, list) else [val]
                        for item in items:
                            assert item in resource_ids, (
                                f"State '{state['id']}' uses unknown resource '{item}' in {case_id}"
                            )

    def test_channels_exist_in_ir(self, case_id: str):
        """Every send/receive channel must exist in ir.json."""
        tla, ir = _load_case(case_id)
        result = parse_translated_tla(tla, ir)

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

    def test_initial_states_match_agents(self, case_id: str):
        """Initial states should cover all agents from ir.json."""
        tla, ir = _load_case(case_id)
        result = parse_translated_tla(tla, ir)

        ir_agent_ids = {a["id"] for a in ir.get("agents", [])}
        assert set(result.initial_states.keys()) == ir_agent_ids, (
            f"Initial states mismatch in {case_id}: "
            f"expected {ir_agent_ids}, got {set(result.initial_states.keys())}"
        )

    def test_every_agent_has_states(self, case_id: str):
        """Every IR agent should have at least one state."""
        tla, ir = _load_case(case_id)
        result = parse_translated_tla(tla, ir)

        ir_agent_ids = {a["id"] for a in ir.get("agents", [])}
        agents_with_states = {s["agent"] for s in result.states}
        assert ir_agent_ids == agents_with_states, (
            f"Agent coverage mismatch in {case_id}: "
            f"IR has {ir_agent_ids}, states have {agents_with_states}"
        )

    def test_no_standalone_labels(self, case_id: str):
        """Labels should only appear inside receive dicts, never as standalone fields."""
        tla, ir = _load_case(case_id)
        result = parse_translated_tla(tla, ir)

        for state in result.states:
            for action in state.get("actions", []):
                assert "label" not in action, (
                    f"State '{state['id']}' has standalone label "
                    f"'{action.get('label')}' in {case_id} — labels should "
                    f"only appear inside receive dicts"
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
# Tests for receive-dispatch merge fixes (multi-action + variable match)
# ===================================================================

class TestMultiActionMerge4M:
    """4M: Multi-action source states (nondeterministic receive from 2 channels)
    should merge each action independently with its dispatch target."""

    @pytest.fixture(scope="class")
    def result(self) -> ParseResult:
        tla, ir = _load_case("4M")
        return parse_translated_tla(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_rv_recv_merged(self, result: ParseResult):
        """rv_recv (reviewer receive) should have 4 actions after merge:
        2 channels × 2 labels each (done + review_request)."""
        rv_recv = next(s for s in result.states if s["id"] == "rv_recv")
        assert len(rv_recv["actions"]) == 4
        # All actions should have receive with channel and label
        for a in rv_recv["actions"]:
            assert "receive" in a
            assert "channel" in a["receive"]
            assert "label" in a["receive"]
        # Channels should be the 2 dev-to-reviewer channels
        channels = {a["receive"]["channel"] for a in rv_recv["actions"]}
        assert len(channels) == 2

    def test_rv_dispatch_states_removed(self, result: ParseResult):
        """rv_handleA and rv_handleB should be merged away."""
        assert "rv_handleA" in result.merged_state_ids or \
               not any(s["id"] == "rv_handleA" for s in result.states)
        assert "rv_handleB" in result.merged_state_ids or \
               not any(s["id"] == "rv_handleB" for s in result.states)

    def test_ts_recv_merged(self, result: ParseResult):
        """ts_recv (tester receive) should have 4 actions after merge."""
        ts_recv = next(s for s in result.states if s["id"] == "ts_recv")
        assert len(ts_recv["actions"]) == 4
        channels = {a["receive"]["channel"] for a in ts_recv["actions"]}
        assert len(channels) == 2

    def test_dev_wait_states_merged(self, result: ParseResult):
        """Developer wait states (single-action source) should still merge."""
        for prefix in ("da", "db"):
            for suffix in ("wait_review", "wait_test", "wait_arch"):
                sid = f"{prefix}_{suffix}"
                state = next((s for s in result.states if s["id"] == sid), None)
                if state:
                    # Each merged wait should have 2 actions with receive+label
                    assert len(state["actions"]) == 2
                    for a in state["actions"]:
                        assert "receive" in a
                        assert "label" in a["receive"]


class TestInDegreeDedupMerge11M:
    """11M: Multi-action source with both actions targeting the same dispatch state.
    In-degree should count unique source states, not edge count."""

    @pytest.fixture(scope="class")
    def result(self) -> ParseResult:
        tla, ir = _load_case("11M")
        return parse_translated_tla(tla, ir)

    def test_no_errors(self, result: ParseResult):
        assert result.errors == []

    def test_worker_dispatch_merged(self, result: ParseResult):
        """wa_j1_check should be merged despite 2 edges from same source state."""
        assert "wa_j1_check" in result.merged_state_ids

    def test_all_worker_dispatches_merged(self, result: ParseResult):
        """All 12 worker dispatch states (*_check) should be merged."""
        for prefix in ("wa", "wb", "wc"):
            for suffix in ("j1_check", "j2_check", "s1_check", "s2_check"):
                sid = f"{prefix}_{suffix}"
                assert sid in result.merged_state_ids, f"{sid} should be merged"

    def test_synthetic_same_target_dedup(self):
        """Synthetic: 2 actions from same state pointing to same target → in-degree 1."""
        from tracefix.pipeline.pipeline.tla_parser import _merge_receive_dispatch

        states = [
            {
                "id": "src",
                "agent": "w",
                "actions": [
                    {"next_state": "dispatch", "receive": {"channel": "ch1", "_recv_var": "msg"}},
                    {"next_state": "dispatch", "receive": {"channel": "ch2", "_recv_var": "msg"}},
                ],
            },
            {
                "id": "dispatch",
                "agent": "w",
                "actions": [
                    {"next_state": "a", "_label": "pass", "_cond_var": "msg"},
                    {"next_state": "b", "_label": "fail", "_cond_var": "msg"},
                ],
            },
        ]
        result, merged = _merge_receive_dispatch(states)
        assert "dispatch" in merged
        src = next(s for s in result if s["id"] == "src")
        assert len(src["actions"]) == 4  # 2 channels × 2 labels


class TestVariableMismatchMerge:
    """Variable mismatch: when receive assigns to var_x but dispatch checks var_y,
    merge should be skipped."""

    def test_no_merge_on_variable_mismatch(self):
        """Synthetic test: source receives into 'revD' but target checks 'revA'."""
        from tracefix.pipeline.pipeline.tla_parser import _merge_receive_dispatch

        states = [
            {
                "id": "src",
                "agent": "editor",
                "actions": [
                    {
                        "next_state": "dispatch",
                        "receive": {"channel": "ch1", "_recv_var": "revD"},
                    }
                ],
            },
            {
                "id": "dispatch",
                "agent": "editor",
                "actions": [
                    {
                        "next_state": "accept",
                        "_label": "approve",
                        "_cond_var": "revA",  # different from revD!
                    },
                    {
                        "next_state": "reject",
                        "_label": "reject",
                        "_cond_var": "revA",
                    },
                ],
            },
        ]
        result, merged = _merge_receive_dispatch(states)
        # dispatch should NOT be merged because revD != revA
        assert "dispatch" not in merged
        assert len(result) == 2
        # src should still have its original single action
        src = next(s for s in result if s["id"] == "src")
        assert len(src["actions"]) == 1

    def test_merge_when_variables_match(self):
        """Synthetic test: source receives into 'msg' and target checks 'msg'."""
        from tracefix.pipeline.pipeline.tla_parser import _merge_receive_dispatch

        states = [
            {
                "id": "src",
                "agent": "editor",
                "actions": [
                    {
                        "next_state": "dispatch",
                        "receive": {"channel": "ch1", "_recv_var": "msg"},
                    }
                ],
            },
            {
                "id": "dispatch",
                "agent": "editor",
                "actions": [
                    {
                        "next_state": "accept",
                        "_label": "approve",
                        "_cond_var": "msg",
                    },
                    {
                        "next_state": "reject",
                        "_label": "reject",
                        "_cond_var": "msg",
                    },
                ],
            },
        ]
        result, merged = _merge_receive_dispatch(states)
        assert "dispatch" in merged
        src = next(s for s in result if s["id"] == "src")
        assert len(src["actions"]) == 2

    def test_merge_when_no_recv_var(self):
        """Backward compat: if _recv_var is absent, merge should still work."""
        from tracefix.pipeline.pipeline.tla_parser import _merge_receive_dispatch

        states = [
            {
                "id": "src",
                "agent": "x",
                "actions": [
                    {
                        "next_state": "dispatch",
                        "receive": {"channel": "ch1"},  # no _recv_var
                    }
                ],
            },
            {
                "id": "dispatch",
                "agent": "x",
                "actions": [
                    {"next_state": "a", "_label": "foo", "_cond_var": "msg"},
                    {"next_state": "b", "_label": "bar", "_cond_var": "msg"},
                ],
            },
        ]
        result, merged = _merge_receive_dispatch(states)
        assert "dispatch" in merged


class TestRecvVarExtraction:
    """_recv_var should be extracted from Head() pattern in receives."""

    def test_recv_var_in_parsed_receive(self):
        """parse_operator should produce receives with _recv_var."""
        from tracefix.pipeline.pipeline.tla_parser import (
            build_ir_metadata, extract_translation_block, split_operators,
            parse_operator,
        )
        tla, ir = _load_case("10E")
        block = extract_translation_block(tla)
        meta = build_ir_metadata(ir)
        ops = dict(split_operators(block))
        # bb_wait_notify receives from a_to_b into msg_b
        actions = parse_operator("bb_wait_notify", ops["bb_wait_notify"], meta)
        assert len(actions) == 1
        assert actions[0].receives[0].get("_recv_var") == "msg_b"

    def test_recv_var_cleaned_in_final_output(self):
        """_recv_var should not appear in final parse result."""
        tla, ir = _load_case("10E")
        result = parse_translated_tla(tla, ir)
        for state in result.states:
            for action in state.get("actions", []):
                recv = action.get("receive")
                if isinstance(recv, dict):
                    assert "_recv_var" not in recv


class TestCondVarExtraction:
    """cond_var should be extracted from IF conditions with message labels."""

    def test_cond_var_in_parsed_action(self):
        """parse_operator should set cond_var on label-bearing actions."""
        from tracefix.pipeline.pipeline.tla_parser import (
            build_ir_metadata, extract_translation_block, split_operators,
            parse_operator,
        )
        tla, ir = _load_case("10E")
        block = extract_translation_block(tla)
        meta = build_ir_metadata(ir)
        ops = dict(split_operators(block))
        # bb_check: IF msg_b = "types_updated" THEN rebuild ELSE done
        actions = parse_operator("bb_check", ops["bb_check"], meta)
        assert len(actions) == 2
        then_action = next(a for a in actions if a.label == "types_updated")
        assert then_action.cond_var == "msg_b"

    def test_cond_var_none_for_non_label(self):
        """Loop guards should NOT set cond_var."""
        from tracefix.pipeline.pipeline.tla_parser import (
            build_ir_metadata, extract_translation_block, split_operators,
            parse_operator,
        )
        tla, ir = _load_case("11H")
        block = extract_translation_block(tla)
        meta = build_ir_metadata(ir)
        ops = dict(split_operators(block))
        # in_loop: IF passed < 8 THEN ... ELSE ... (loop guard, not label)
        actions = parse_operator("in_loop", ops["in_loop"], meta)
        for a in actions:
            assert a.cond_var is None

    def test_cond_var_cleaned_in_final_output(self):
        """_cond_var should not appear in final parse result."""
        tla, ir = _load_case("10E")
        result = parse_translated_tla(tla, ir)
        for state in result.states:
            for action in state.get("actions", []):
                assert "_cond_var" not in action


class TestInferElseLabelsMultiChannel:
    """_infer_else_labels should group by channel for multi-channel states."""

    def test_infer_per_channel(self):
        """Synthetic: state with 2 channels, each missing 1 label."""
        from tracefix.pipeline.pipeline.tla_parser import _infer_else_labels

        states = [
            {
                "id": "s1",
                "actions": [
                    {"receive": {"channel": "ch_a", "label": "foo"}},
                    {"receive": {"channel": "ch_a"}},  # missing label
                    {"receive": {"channel": "ch_b", "label": "x"}},
                    {"receive": {"channel": "ch_b"}},  # missing label
                ],
            },
        ]
        ir_data = {
            "channels": [
                {"id": "ch_a", "labels": ["foo", "bar"]},
                {"id": "ch_b", "labels": ["x", "y"]},
            ],
        }
        count = _infer_else_labels(states, ir_data)
        assert count == 2
        # ch_a unlabeled should get "bar"
        ch_a_actions = [a for a in states[0]["actions"]
                        if a["receive"].get("channel") == "ch_a"]
        labels_a = {a["receive"]["label"] for a in ch_a_actions}
        assert labels_a == {"foo", "bar"}
        # ch_b unlabeled should get "y"
        ch_b_actions = [a for a in states[0]["actions"]
                        if a["receive"].get("channel") == "ch_b"]
        labels_b = {a["receive"]["label"] for a in ch_b_actions}
        assert labels_b == {"x", "y"}
