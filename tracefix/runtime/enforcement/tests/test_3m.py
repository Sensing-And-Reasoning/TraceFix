"""Tests for tracefix.runtime.enforcement with 3M research writing protocol (5 agents, 2 locks, 13 channels).

The 3M protocol (IRs/3M/) models collaborative research writing:
  - 3 researchers write sections (doc_lock), gather references (ref_lock), submit to fact checker
  - Factchecker reviews submissions (pass/flag), flagged researchers revise and resubmit
  - Editor collects all passed notifications, reviews for consistency, accepts or requests revision
  - Researchers who receive "revise" from editor resubmit, then get final "accept"

The IR in IRs/3M/ only has topology (agents, resources, channels) because it uses the PlusCal
pipeline. This test builds the complete IR with states by translating Protocol.tla's PlusCal
into IR state machines. Boolean flags (doneA/B/C, gotA/B/C) are encoded as explicit states.
"""

from itertools import product

import pytest

from tracefix.runtime.enforcement.engine import run_ir, RunResult
from tracefix.runtime.enforcement.policy import AgentPolicy


# ---------------------------------------------------------------------------
# IR builder: translate Protocol.tla PlusCal → IR states
# ---------------------------------------------------------------------------

def _build_researcher_states(prefix: str, agent_id: str, channels: dict) -> list[dict]:
    """Build IR states for one researcher (A, B, or C).

    Channels dict keys: res_to_fc, fc_to_res, editor_to_res, res_to_editor
    """
    return [
        # Write section — acquire doc_lock
        {
            "id": f"{prefix}_write", "agent": agent_id,
            "actions": [{"target": f"{prefix}_rel_doc", "acquire": ["doc_lock"]}],
        },
        {
            "id": f"{prefix}_rel_doc", "agent": agent_id,
            "actions": [{"target": f"{prefix}_ref", "release": ["doc_lock"]}],
        },
        # Gather references — acquire ref_lock
        {
            "id": f"{prefix}_ref", "agent": agent_id,
            "actions": [{"target": f"{prefix}_rel_ref", "acquire": ["ref_lock"]}],
        },
        {
            "id": f"{prefix}_rel_ref", "agent": agent_id,
            "actions": [{
                "target": f"{prefix}_wait_fc",
                "release": ["ref_lock"],
                "send": [{"channel": channels["res_to_fc"], "label": "submit"}],
            }],
        },
        # Wait for fact checker: flag → loop back, pass → continue
        {
            "id": f"{prefix}_wait_fc", "agent": agent_id,
            "actions": [
                {
                    "target": f"{prefix}_write",
                    "receive": [{"channel": channels["fc_to_res"], "label": "flag"}],
                },
                {
                    "target": f"{prefix}_wait_ed",
                    "receive": [{"channel": channels["fc_to_res"], "label": "pass"}],
                },
            ],
        },
        # Wait for editor: accept → done, revise → revision loop
        {
            "id": f"{prefix}_wait_ed", "agent": agent_id,
            "actions": [
                {
                    "target": f"{prefix}_done",
                    "receive": [{"channel": channels["editor_to_res"], "label": "accept"}],
                },
                {
                    "target": f"{prefix}_revise",
                    "receive": [{"channel": channels["editor_to_res"], "label": "revise"}],
                },
            ],
        },
        # Revision: acquire doc_lock, edit, release, resubmit to editor
        {
            "id": f"{prefix}_revise", "agent": agent_id,
            "actions": [{"target": f"{prefix}_rev_rel", "acquire": ["doc_lock"]}],
        },
        {
            "id": f"{prefix}_rev_rel", "agent": agent_id,
            "actions": [{
                "target": f"{prefix}_wait_ed2",
                "release": ["doc_lock"],
                "send": [{"channel": channels["res_to_editor"], "label": "resubmit"}],
            }],
        },
        # Wait for final accept after resubmission
        {
            "id": f"{prefix}_wait_ed2", "agent": agent_id,
            "actions": [{
                "target": f"{prefix}_done",
                "receive": [{"channel": channels["editor_to_res"], "label": "accept"}],
            }],
        },
        # Terminal
        {"id": f"{prefix}_done", "agent": agent_id, "actions": []},
    ]


def _build_factchecker_states() -> list[dict]:
    """Build factchecker states with boolean-encoded (doneA, doneB, doneC).

    Each combination (except all-done) becomes a state. From each state,
    the factchecker can receive from any not-yet-done researcher and
    nondeterministically pass or flag them.
    """
    researchers = [
        # (index, recv_channel, send_channel, passed_label)
        (0, "resA_to_fc", "fc_to_resA", "passedA"),
        (1, "resB_to_fc", "fc_to_resB", "passedB"),
        (2, "resC_to_fc", "fc_to_resC", "passedC"),
    ]

    states = []
    for combo in product([0, 1], repeat=3):
        if combo == (1, 1, 1):
            continue  # terminal state handled separately

        suffix = "".join(str(d) for d in combo)
        state_id = f"fc_recv_{suffix}"
        actions = []

        for idx, recv_ch, send_ch, passed_label in researchers:
            if combo[idx] == 1:
                continue  # this researcher already passed

            # Compute next state when passing
            new_combo = list(combo)
            new_combo[idx] = 1
            new_suffix = "".join(str(d) for d in new_combo)
            pass_target = "fc_done" if all(d == 1 for d in new_combo) else f"fc_recv_{new_suffix}"

            # Pass: send "pass" to researcher + "passedX" to editor
            actions.append({
                "target": pass_target,
                "receive": [{"channel": recv_ch, "label": "submit"}],
                "send": [
                    {"channel": send_ch, "label": "pass"},
                    {"channel": "fc_to_editor", "label": passed_label},
                ],
            })
            # Flag: send "flag" to researcher (they'll revise and resubmit)
            actions.append({
                "target": state_id,  # stay in same state
                "receive": [{"channel": recv_ch, "label": "submit"}],
                "send": [{"channel": send_ch, "label": "flag"}],
            })

        states.append({"id": state_id, "agent": "factchecker", "actions": actions})

    states.append({"id": "fc_done", "agent": "factchecker", "actions": []})
    return states


def _build_editor_states() -> list[dict]:
    """Build editor states: collect phase (boolean-encoded) + review/revision phase."""
    labels_map = [
        # (index, receive_label)
        (0, "passedA"),
        (1, "passedB"),
        (2, "passedC"),
    ]

    states = []

    # --- Collect phase: wait for all 3 "passedX" from fc_to_editor ---
    for combo in product([0, 1], repeat=3):
        if combo == (1, 1, 1):
            continue  # all collected → transition to review

        suffix = "".join(str(d) for d in combo)
        state_id = f"ed_collect_{suffix}"
        actions = []

        for idx, label in labels_map:
            if combo[idx] == 1:
                continue  # already received this one

            new_combo = list(combo)
            new_combo[idx] = 1
            new_suffix = "".join(str(d) for d in new_combo)
            target = "ed_review" if all(d == 1 for d in new_combo) else f"ed_collect_{new_suffix}"

            actions.append({
                "target": target,
                "receive": [{"channel": "fc_to_editor", "label": label}],
            })

        states.append({"id": state_id, "agent": "editor", "actions": actions})

    # --- Review phase ---
    states.extend([
        # Acquire doc_lock for review
        {
            "id": "ed_review", "agent": "editor",
            "actions": [{"target": "ed_decide", "acquire": ["doc_lock"]}],
        },
        # Nondeterministic: accept all or revise all
        {
            "id": "ed_decide", "agent": "editor",
            "actions": [
                # Accept all researchers
                {
                    "target": "ed_done",
                    "release": ["doc_lock"],
                    "send": [
                        {"channel": "editor_to_resA", "label": "accept"},
                        {"channel": "editor_to_resB", "label": "accept"},
                        {"channel": "editor_to_resC", "label": "accept"},
                    ],
                },
                # Revise all researchers
                {
                    "target": "ed_resub_000",
                    "release": ["doc_lock"],
                    "send": [
                        {"channel": "editor_to_resA", "label": "revise"},
                        {"channel": "editor_to_resB", "label": "revise"},
                        {"channel": "editor_to_resC", "label": "revise"},
                    ],
                },
            ],
        },
    ])

    # Wait for resubmissions (nondeterministic: any order, mirrors collect phase)
    resub_channels = [
        (0, "resA_to_editor"),
        (1, "resB_to_editor"),
        (2, "resC_to_editor"),
    ]
    for combo in product([0, 1], repeat=3):
        if combo == (1, 1, 1):
            continue  # all resubmitted → transition to ed_finalize
        suffix = "".join(str(d) for d in combo)
        state_id = f"ed_resub_{suffix}"
        actions = []
        for idx, channel in resub_channels:
            if combo[idx] == 1:
                continue  # already received from this researcher
            new_combo = list(combo)
            new_combo[idx] = 1
            new_suffix = "".join(str(d) for d in new_combo)
            target = "ed_finalize" if all(d == 1 for d in new_combo) else f"ed_resub_{new_suffix}"
            actions.append({
                "target": target,
                "receive": [{"channel": channel, "label": "resubmit"}],
            })
        states.append({"id": state_id, "agent": "editor", "actions": actions})

    states.extend([
        # Finalize: re-acquire doc_lock, then accept all
        {
            "id": "ed_finalize", "agent": "editor",
            "actions": [{"target": "ed_fin_rel", "acquire": ["doc_lock"]}],
        },
        {
            "id": "ed_fin_rel", "agent": "editor",
            "actions": [{
                "target": "ed_done",
                "release": ["doc_lock"],
                "send": [
                    {"channel": "editor_to_resA", "label": "accept"},
                    {"channel": "editor_to_resB", "label": "accept"},
                    {"channel": "editor_to_resC", "label": "accept"},
                ],
            }],
        },
        # Terminal
        {"id": "ed_done", "agent": "editor", "actions": []},
    ])

    return states


def build_3m_ir() -> dict:
    """Build the complete 3M research writing IR with all states.

    Translates IRs/3M/Protocol.tla PlusCal into IR state machines:
    - 3 researchers: symmetric write→ref→submit→review cycle with revision loops
    - 1 factchecker: boolean-encoded states tracking which researchers passed
    - 1 editor: boolean-encoded collect phase + nondeterministic accept/revise
    """
    ir = {
        "agents": [
            {"id": "researcherA", "initial_state": "ra_write"},
            {"id": "researcherB", "initial_state": "rb_write"},
            {"id": "researcherC", "initial_state": "rc_write"},
            {"id": "factchecker", "initial_state": "fc_recv_000"},
            {"id": "editor", "initial_state": "ed_collect_000"},
        ],
        "resources": [
            {"id": "doc_lock", "type": "Lock"},
            {"id": "ref_lock", "type": "Lock"},
        ],
        "channels": [
            {"id": "resA_to_fc", "from": "researcherA", "to": "factchecker", "labels": ["submit"]},
            {"id": "resB_to_fc", "from": "researcherB", "to": "factchecker", "labels": ["submit"]},
            {"id": "resC_to_fc", "from": "researcherC", "to": "factchecker", "labels": ["submit"]},
            {"id": "fc_to_resA", "from": "factchecker", "to": "researcherA", "labels": ["pass", "flag"]},
            {"id": "fc_to_resB", "from": "factchecker", "to": "researcherB", "labels": ["pass", "flag"]},
            {"id": "fc_to_resC", "from": "factchecker", "to": "researcherC", "labels": ["pass", "flag"]},
            {"id": "fc_to_editor", "from": "factchecker", "to": "editor", "labels": ["passedA", "passedB", "passedC"]},
            {"id": "editor_to_resA", "from": "editor", "to": "researcherA", "labels": ["accept", "revise"]},
            {"id": "editor_to_resB", "from": "editor", "to": "researcherB", "labels": ["accept", "revise"]},
            {"id": "editor_to_resC", "from": "editor", "to": "researcherC", "labels": ["accept", "revise"]},
            {"id": "resA_to_editor", "from": "researcherA", "to": "editor", "labels": ["resubmit"]},
            {"id": "resB_to_editor", "from": "researcherB", "to": "editor", "labels": ["resubmit"]},
            {"id": "resC_to_editor", "from": "researcherC", "to": "editor", "labels": ["resubmit"]},
        ],
        "states": [],
    }

    # 3 symmetric researchers
    for prefix, agent_id, r2fc, fc2r, ed2r, r2ed in [
        ("ra", "researcherA", "resA_to_fc", "fc_to_resA", "editor_to_resA", "resA_to_editor"),
        ("rb", "researcherB", "resB_to_fc", "fc_to_resB", "editor_to_resB", "resB_to_editor"),
        ("rc", "researcherC", "resC_to_fc", "fc_to_resC", "editor_to_resC", "resC_to_editor"),
    ]:
        ir["states"].extend(_build_researcher_states(prefix, agent_id, {
            "res_to_fc": r2fc, "fc_to_res": fc2r,
            "editor_to_res": ed2r, "res_to_editor": r2ed,
        }))

    ir["states"].extend(_build_factchecker_states())
    ir["states"].extend(_build_editor_states())

    return ir


# ---------------------------------------------------------------------------
# IR structure tests
# ---------------------------------------------------------------------------

class TestIRStructure:
    """Verify the built IR is well-formed before testing execution."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = build_3m_ir()

    def test_agent_count(self):
        assert len(self.ir["agents"]) == 5

    def test_resource_count(self):
        assert len(self.ir["resources"]) == 2
        types = {r["id"]: r["type"] for r in self.ir["resources"]}
        assert types == {"doc_lock": "Lock", "ref_lock": "Lock"}

    def test_channel_count(self):
        assert len(self.ir["channels"]) == 13

    def test_state_count(self):
        """3 researchers × 10 + factchecker 8 + editor 19 = 57 states.
        Editor: 7 collect + 2 review + 7 resub (bitmap, any-order) + 3 finalize = 19.
        """
        assert len(self.ir["states"]) == 57

    def test_initial_states_exist(self):
        state_ids = {s["id"] for s in self.ir["states"]}
        for agent in self.ir["agents"]:
            assert agent["initial_state"] in state_ids

    def test_all_targets_exist(self):
        state_ids = {s["id"] for s in self.ir["states"]}
        for state in self.ir["states"]:
            for action in state.get("actions", []):
                assert action["target"] in state_ids, (
                    f"State {state['id']} has action targeting unknown state {action['target']}"
                )

    def test_all_channels_referenced(self):
        """Every channel in the IR is used in at least one send or receive."""
        channel_ids = {ch["id"] for ch in self.ir["channels"]}
        used = set()
        for state in self.ir["states"]:
            for action in state.get("actions", []):
                for s in action.get("send", []):
                    used.add(s["channel"])
                for r in action.get("receive", []):
                    used.add(r["channel"])
        assert used == channel_ids

    def test_all_resources_referenced(self):
        resource_ids = {r["id"] for r in self.ir["resources"]}
        used = set()
        for state in self.ir["states"]:
            for action in state.get("actions", []):
                for rid in action.get("acquire", []):
                    used.add(rid)
                for rid in action.get("release", []):
                    used.add(rid)
        assert used == resource_ids

    def test_terminal_states(self):
        """Each agent has exactly one terminal state."""
        terminals = {}
        for state in self.ir["states"]:
            if not state["actions"]:
                terminals.setdefault(state["agent"], []).append(state["id"])
        for agent in self.ir["agents"]:
            assert len(terminals[agent["id"]]) == 1

    def test_factchecker_state_encoding(self):
        """Verify boolean-encoded factchecker states cover all 7 non-terminal combos."""
        fc_states = [s["id"] for s in self.ir["states"] if s["agent"] == "factchecker"]
        expected = {f"fc_recv_{''.join(str(d) for d in combo)}"
                    for combo in product([0, 1], repeat=3)
                    if combo != (1, 1, 1)}
        expected.add("fc_done")
        assert set(fc_states) == expected

    def test_editor_collect_encoding(self):
        """Verify boolean-encoded editor collect states cover all 7 non-terminal combos."""
        ed_collect = [s["id"] for s in self.ir["states"]
                      if s["agent"] == "editor" and s["id"].startswith("ed_collect_")]
        expected = {f"ed_collect_{''.join(str(d) for d in combo)}"
                    for combo in product([0, 1], repeat=3)
                    if combo != (1, 1, 1)}
        assert set(ed_collect) == expected


# ---------------------------------------------------------------------------
# Execution tests
# ---------------------------------------------------------------------------

class Test3MExecution:
    """Run the 3M protocol through the runtime engine."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = build_3m_ir()

    def test_runs_to_completion(self):
        result = run_ir(self.ir, seed=42, timeout=10)
        assert result.success, f"Failed: {result.error}"

    def test_all_agents_terminate(self):
        result = run_ir(self.ir, seed=42, timeout=10)
        expected = {
            "researcherA": "ra_done",
            "researcherB": "rb_done",
            "researcherC": "rc_done",
            "factchecker": "fc_done",
            "editor": "ed_done",
        }
        assert result.final_states == expected

    def test_deterministic_with_seed(self):
        r1 = run_ir(self.ir, seed=42, timeout=10)
        r2 = run_ir(self.ir, seed=42, timeout=10)
        assert r1.steps == r2.steps
        t1 = [(e.agent, e.from_state, e.to_state) for e in r1.trace]
        t2 = [(e.agent, e.from_state, e.to_state) for e in r2.trace]
        assert t1 == t2

    def test_different_seeds_explore_paths(self):
        """Different seeds should produce different execution paths."""
        results = [run_ir(self.ir, seed=s, timeout=10) for s in range(30)]
        assert all(r.success for r in results), \
            f"Failures: {[(s, r.error) for s, r in enumerate(results) if not r.success]}"
        step_counts = {r.steps for r in results}
        assert len(step_counts) > 1, "All seeds produced identical step counts"

    def test_trace_nonempty(self):
        result = run_ir(self.ir, seed=42, timeout=10)
        assert result.steps > 0
        assert len(result.trace) == result.steps

    def test_valid_transitions(self):
        """Every trace event follows a valid action from its from_state."""
        result = run_ir(self.ir, seed=42, timeout=10)
        states = {s["id"]: s for s in self.ir["states"]}
        for event in result.trace:
            assert event.from_state in states, f"Unknown from_state: {event.from_state}"
            sdef = states[event.from_state]
            targets = [a["target"] for a in sdef["actions"]]
            assert event.to_state in targets, (
                f"Invalid transition: {event.from_state} → {event.to_state}, "
                f"valid targets: {targets}"
            )

    def test_agent_ownership(self):
        """Each trace event's agent matches the from_state's owner."""
        result = run_ir(self.ir, seed=42, timeout=10)
        states = {s["id"]: s for s in self.ir["states"]}
        for event in result.trace:
            assert states[event.from_state]["agent"] == event.agent

    def test_duration_fast(self):
        result = run_ir(self.ir, seed=42, timeout=10)
        assert result.duration < 1.0  # in-memory should be <100ms


# ---------------------------------------------------------------------------
# Invariant tests (TLC-equivalent safety properties)
# ---------------------------------------------------------------------------

class Test3MInvariants:
    """Verify TLC-equivalent invariants at runtime."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = build_3m_ir()

    def _run(self, seed=42) -> RunResult:
        result = run_ir(self.ir, seed=seed, timeout=10)
        assert result.success, f"Execution failed: {result.error}"
        return result

    def test_no_orphan_locks(self):
        """All locks are free after termination (NoOrphanLocks invariant)."""
        result = self._run()
        for lock_id, holder in result.final_locks.items():
            assert holder is None, f"Lock {lock_id} still held by {holder}"

    def test_channels_drained(self):
        """All channels are empty after termination (ChannelsDrained invariant)."""
        result = self._run()
        for ch_id, length in result.final_channels.items():
            assert length == 0, f"Channel {ch_id} has {length} unconsumed messages"

    def test_mutual_exclusion_doc_lock(self):
        """doc_lock is never held by two agents simultaneously."""
        result = self._run()
        holder = None
        for event in result.trace:
            for g in event.guards:
                if "acquire(doc_lock)" in g:
                    assert holder is None, (
                        f"Step {event.step}: {event.agent} acquired doc_lock "
                        f"but {holder} already holds it"
                    )
                    holder = event.agent
            for ef in event.effects:
                if "release(doc_lock)" in ef:
                    assert holder == event.agent, (
                        f"Step {event.step}: {event.agent} released doc_lock "
                        f"but {holder} holds it"
                    )
                    holder = None

    def test_mutual_exclusion_ref_lock(self):
        """ref_lock is never held by two agents simultaneously."""
        result = self._run()
        holder = None
        for event in result.trace:
            for g in event.guards:
                if "acquire(ref_lock)" in g:
                    assert holder is None, (
                        f"Step {event.step}: {event.agent} acquired ref_lock "
                        f"but {holder} already holds it"
                    )
                    holder = event.agent
            for ef in event.effects:
                if "release(ref_lock)" in ef:
                    assert holder == event.agent, (
                        f"Step {event.step}: {event.agent} released ref_lock "
                        f"but {holder} holds it"
                    )
                    holder = None

    def test_invariants_across_seeds(self):
        """NoOrphanLocks + ChannelsDrained hold across many seeds."""
        for seed in range(50):
            result = run_ir(self.ir, seed=seed, timeout=10)
            assert result.success, f"Seed {seed} failed: {result.error}"
            for lock_id, holder in result.final_locks.items():
                assert holder is None, f"Seed {seed}: lock {lock_id} held by {holder}"
            for ch_id, length in result.final_channels.items():
                assert length == 0, f"Seed {seed}: channel {ch_id} has {length} messages"


# ---------------------------------------------------------------------------
# Protocol semantics tests
# ---------------------------------------------------------------------------

class Test3MSemantics:
    """Verify high-level protocol semantics."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = build_3m_ir()

    def _run(self, seed=42) -> RunResult:
        result = run_ir(self.ir, seed=seed, timeout=10)
        assert result.success, f"Execution failed: {result.error}"
        return result

    def test_factchecker_processes_all_researchers(self):
        """Factchecker sends passedA/B/C to editor (eventually)."""
        result = self._run()
        fc_sends = [
            ef for event in result.trace
            if event.agent == "factchecker"
            for ef in event.effects
            if ef.startswith("send(fc_to_editor,")
        ]
        labels = {ef.split(",")[1].rstrip(")") for ef in fc_sends}
        assert labels == {"passedA", "passedB", "passedC"}

    def test_editor_sends_accept_to_all(self):
        """Editor eventually sends 'accept' to all 3 researchers."""
        result = self._run()
        accepts = set()
        for event in result.trace:
            if event.agent == "editor":
                for ef in event.effects:
                    if ef.startswith("send(editor_to_res") and "accept" in ef:
                        # Extract channel: "send(editor_to_resA,accept)" → "editor_to_resA"
                        ch = ef.split("(")[1].split(",")[0]
                        accepts.add(ch)
        assert accepts == {"editor_to_resA", "editor_to_resB", "editor_to_resC"}

    def test_researchers_submit_before_factcheck(self):
        """Each researcher submits to factchecker before factchecker reviews them."""
        result = self._run()
        for prefix, fc_ch in [("researcherA", "resA_to_fc"),
                               ("researcherB", "resB_to_fc"),
                               ("researcherC", "resC_to_fc")]:
            submit_step = next(
                (e.step for e in result.trace
                 if e.agent == prefix and f"send({fc_ch},submit)" in e.effects),
                None,
            )
            fc_recv_step = next(
                (e.step for e in result.trace
                 if e.agent == "factchecker" and f"recv({fc_ch},submit)" in e.guards),
                None,
            )
            assert submit_step is not None, f"{prefix} never submitted"
            assert fc_recv_step is not None, f"factchecker never received from {prefix}"
            assert submit_step < fc_recv_step

    def test_revision_path_exists(self):
        """Across many seeds, at least one execution includes a revision loop."""
        saw_flag = False
        saw_revise = False
        for seed in range(50):
            result = run_ir(self.ir, seed=seed, timeout=10)
            if not result.success:
                continue
            for event in result.trace:
                for ef in event.effects:
                    if "flag" in ef:
                        saw_flag = True
                    if "revise" in ef:
                        saw_revise = True
        assert saw_flag, "No factchecker flag seen across 50 seeds"
        assert saw_revise, "No editor revise seen across 50 seeds"

    def test_min_steps_accept_all(self):
        """Best case: all pass first try, editor accepts immediately.
        Researchers: 4 steps each (write→rel→ref→rel_ref_submit) + wait_fc + wait_ed = 6
        Factchecker: 3 passes = 3 steps + terminal = 4 (but enters each recv state)
        Actually count precisely from trace with many seeds.
        """
        min_steps = min(
            run_ir(self.ir, seed=s, timeout=10).steps
            for s in range(100)
        )
        # At minimum: each researcher does 4+1+1=6 steps (write,rel_doc,ref,rel_ref,wait_fc,wait_ed)
        # factchecker: 3 recv+pass transitions + done = 3
        # editor: 3 collects + review + decide(accept) + done = 5 steps
        # Total minimum: 18 + 3 + 5 = 26 but with interleavings, at least this many
        assert min_steps >= 20, f"Unexpectedly few steps: {min_steps}"


# ---------------------------------------------------------------------------
# Stress tests
# ---------------------------------------------------------------------------

class Test3MStress:
    """Run many seeds to check robustness."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = build_3m_ir()

    def test_100_seeds_all_succeed(self):
        failures = []
        for seed in range(100):
            result = run_ir(self.ir, seed=seed, timeout=10)
            if not result.success:
                failures.append((seed, result.error))
        assert not failures, f"Failed seeds: {failures}"

    def test_step_count_distribution(self):
        """Verify step counts vary (different nondeterministic paths)."""
        counts = [run_ir(self.ir, seed=s, timeout=10).steps for s in range(50)]
        unique = set(counts)
        assert len(unique) >= 3, f"Only {len(unique)} unique step counts: {sorted(unique)}"
        # Min should be around 25-35 (happy path), max can be higher (with flags + revisions)
        assert min(counts) < max(counts)


# ---------------------------------------------------------------------------
# Tool-driven policy: Document3MPolicy
# ---------------------------------------------------------------------------

import asyncio
import random as _random

import importlib as _importlib

from benchmark.tools._base import ToolConfig, ToolResult
from benchmark.tools import load_tools

_sim_3m_mod = _importlib.import_module("benchmark.environments.3M.sim")
_MultiAuthorPaperSim = _sim_3m_mod.MultiAuthorPaperSim


# Researcher prefix → section name mapping
_RESEARCHER_SECTION = {
    "ra": "section_A",
    "rb": "section_B",
    "rc": "section_C",
}

# Factchecker recv channel → researcher name for fact_check
_FC_RECV_TO_SECTION = {
    "resA_to_fc": "section_A",
    "resB_to_fc": "section_B",
    "resC_to_fc": "section_C",
}


class Document3MPolicy:
    """Tool-driven policy for the 3M research writing protocol.

    - Researchers: fire-and-forget tool calls at each state
    - Factchecker: calls fact_check, uses success/failure to pick pass/flag
    - Editor: calls review_sections at ed_decide, uses result to pick accept/revise;
              calls combine_sections at ed_finalize (fire-and-forget)

    Args:
        config: ToolConfig controlling delay and fail_probability.
        rng: Random instance for scheduling decisions.
        max_fails: Maximum number of tool failures per (tool, key) before
                   forcing success.  None = unlimited (use tool result as-is).
    """

    def __init__(self, config: ToolConfig, rng: _random.Random | None = None,
                 max_fails: int | None = None):
        sim = _MultiAuthorPaperSim()
        sim._delay_multiplier = 0.0
        if config.fail_probability > 0:
            sim.set_decision_fail_rate(config.fail_probability)
        self._registry = load_tools("3M", config, sim=sim)
        self._config = config
        self._rng = rng or _random.Random()
        self._max_fails = max_fails
        self._fail_counts: dict[tuple[str, str], int] = {}  # (tool, key) → count

    def _is_success(self, result: ToolResult, key: str) -> bool:
        """Check if a tool result counts as success, respecting max_fails.

        After max_fails failures for a given (tool_name, key), force success
        so the protocol can always terminate.
        """
        if result.success:
            return True
        if self._max_fails is None:
            return False
        counter_key = (result.tool_name, key)
        self._fail_counts[counter_key] = self._fail_counts.get(counter_key, 0) + 1
        if self._fail_counts[counter_key] > self._max_fails:
            return True  # force success after max_fails
        return False

    async def choose_action(
        self,
        agent_id: str,
        state_id: str,
        enabled_actions: list[dict],
        *,
        context: list[dict] | None = None,
    ) -> tuple[int, list[dict]]:
        tool_calls: list[dict] = []

        # --- Researcher states: fire-and-forget ---
        prefix = None
        for pfx in ("ra", "rb", "rc"):
            if state_id.startswith(pfx + "_"):
                prefix = pfx
                break

        if prefix is not None:
            section = _RESEARCHER_SECTION[prefix]
            suffix = state_id[len(prefix) + 1:]  # e.g. "write", "ref", "revise", etc.

            if suffix == "write":
                result = await self._registry.call("write_section", agent_id=agent_id, section_name=section)
                tool_calls.append(result.to_dict())
            elif suffix == "ref":
                result = await self._registry.call("research_topic", agent_id=agent_id, topic=section)
                tool_calls.append(result.to_dict())
            elif suffix in ("rel_ref",):
                result = await self._registry.call("update_references", agent_id=agent_id, section_name=section)
                tool_calls.append(result.to_dict())
            elif suffix == "revise":
                result = await self._registry.call("revise_section", agent_id=agent_id, section_name=section)
                tool_calls.append(result.to_dict())

            # Single action or random for researchers (no tool-driven decision)
            idx = 0 if len(enabled_actions) == 1 else self._rng.randrange(len(enabled_actions))
            return idx, tool_calls

        # --- Factchecker states (fc_recv_*): tool-driven decision ---
        if state_id.startswith("fc_recv_"):
            # Group enabled actions by receive channel to identify which researcher
            # Pick one researcher randomly (scheduling), then use fact_check result
            # to choose pass vs flag for that researcher
            #
            # Enabled actions come in pairs: (pass, flag) per researcher with pending submit
            # We need to identify which researcher's submit to process
            recv_channels = set()
            for a in enabled_actions:
                for r in a.get("receive", []):
                    recv_channels.add(r["channel"])

            # Pick a channel randomly (scheduling fairness)
            chosen_channel = self._rng.choice(sorted(recv_channels))
            section = _FC_RECV_TO_SECTION[chosen_channel]

            # Call fact_check
            result = await self._registry.call("fact_check", agent_id=agent_id, section_name=section)
            tool_calls.append(result.to_dict())

            # Find the matching actions for this channel
            channel_actions = [
                (i, a) for i, a in enumerate(enabled_actions)
                if any(r["channel"] == chosen_channel for r in a.get("receive", []))
            ]

            if self._is_success(result, section):
                # Pick the "pass" action (has send with label="pass")
                for i, a in channel_actions:
                    sends = a.get("send", [])
                    if any(s.get("label") == "pass" for s in sends):
                        return i, tool_calls
            else:
                # Pick the "flag" action (has send with label="flag")
                for i, a in channel_actions:
                    sends = a.get("send", [])
                    if any(s.get("label") == "flag" for s in sends):
                        return i, tool_calls

            # Fallback (shouldn't reach here)
            return channel_actions[0][0], tool_calls

        # --- Editor states ---
        if state_id == "ed_decide":
            # Call review_sections to decide accept vs revise
            result = await self._registry.call("review_sections", agent_id=agent_id, section_name="all")
            tool_calls.append(result.to_dict())

            if self._is_success(result, "all"):
                # Accept: find action with send label="accept"
                for i, a in enumerate(enabled_actions):
                    sends = a.get("send", [])
                    if any(s.get("label") == "accept" for s in sends):
                        return i, tool_calls
            else:
                # Revise: find action with send label="revise"
                for i, a in enumerate(enabled_actions):
                    sends = a.get("send", [])
                    if any(s.get("label") == "revise" for s in sends):
                        return i, tool_calls

            return 0, tool_calls

        if state_id == "ed_finalize":
            # Fire-and-forget: combine sections
            result = await self._registry.call("combine_sections", agent_id=agent_id, sections="A,B,C")
            tool_calls.append(result.to_dict())
            return 0, tool_calls

        # --- Default: single action or random ---
        idx = 0 if len(enabled_actions) == 1 else self._rng.randrange(len(enabled_actions))
        return idx, tool_calls


# ---------------------------------------------------------------------------
# Tool-driven tests
# ---------------------------------------------------------------------------

class Test3MToolDriven:
    """Run the 3M protocol with Document3MPolicy calling simulated tools."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = build_3m_ir()

    def _run(self, fail_probability: float = 0.3, seed: int = 42) -> RunResult:
        cfg = ToolConfig(min_delay=0, max_delay=0, fail_probability=fail_probability)
        # Use a different seed for the policy RNG so that engine scheduling
        # randomness and tool-failure randomness advance independently.
        rng = _random.Random(seed + 1)
        policy = Document3MPolicy(cfg, rng=rng)
        result = run_ir(self.ir, seed=seed, timeout=10, policy=policy)
        assert result.success, f"Failed: {result.error}"
        return result

    def test_tool_calls_in_trace(self):
        """Verify trace events contain tool_call records."""
        result = self._run(fail_probability=0.3)
        events_with_tools = [e for e in result.trace if e.tool_calls]
        assert len(events_with_tools) > 0, "No tool calls recorded in trace"

    def test_all_pass_no_revisions(self):
        """fail_probability=0: all fact_checks pass, editor accepts → no revision loops."""
        result = self._run(fail_probability=0)
        # No "flag" effects in trace
        for event in result.trace:
            for ef in event.effects:
                assert "flag" not in ef, f"Unexpected flag at step {event.step}"
        # No "revise" effects in trace
        for event in result.trace:
            for ef in event.effects:
                assert "revise" not in ef, f"Unexpected revise at step {event.step}"

    def test_all_fail_revisions(self):
        """fail_probability=1 + max_fails=1: all fact_checks and reviews fail once,
        then succeed on retry → revision loops always triggered."""
        cfg = ToolConfig(min_delay=0, max_delay=0, fail_probability=1)
        rng = _random.Random(42)
        policy = Document3MPolicy(cfg, rng=rng, max_fails=1)
        result = run_ir(self.ir, seed=42, timeout=10, policy=policy)
        assert result.success, f"Failed: {result.error}"
        # Should see "flag" effects (factchecker flagging researchers)
        flags = [e for e in result.trace for ef in e.effects if "flag" in ef]
        assert len(flags) > 0, "Expected factchecker flags with fail_probability=1"
        # Should see "revise" effects (editor requesting revision)
        revises = [e for e in result.trace for ef in e.effects if "revise" in ef]
        assert len(revises) > 0, "Expected editor revise with fail_probability=1"

    def test_mixed_probability(self):
        """fail_probability=0.3: some pass, some flag, run across seeds."""
        for seed in range(20):
            result = self._run(fail_probability=0.3, seed=seed)
            assert result.success, f"Seed {seed} failed: {result.error}"
            # All agents should terminate
            assert len(result.final_states) == 5

    def test_factchecker_calls_fact_check(self):
        """Verify factchecker trace events have fact_check tool calls."""
        result = self._run(fail_probability=0.3)
        fc_events = [e for e in result.trace if e.agent == "factchecker" and e.tool_calls]
        fact_check_calls = [
            tc for e in fc_events for tc in e.tool_calls
            if tc.get("tool_name") == "fact_check"
        ]
        assert len(fact_check_calls) >= 3, (
            f"Expected at least 3 fact_check calls, got {len(fact_check_calls)}"
        )

    def test_editor_calls_review(self):
        """Verify editor ed_decide events have review_sections tool calls."""
        result = self._run(fail_probability=0)
        ed_decide_events = [
            e for e in result.trace
            if e.agent == "editor" and e.from_state == "ed_decide"
        ]
        assert len(ed_decide_events) >= 1
        for event in ed_decide_events:
            review_calls = [tc for tc in event.tool_calls
                            if tc.get("tool_name") == "review_sections"]
            assert len(review_calls) == 1, (
                f"Expected 1 review_sections call at ed_decide, got {len(review_calls)}"
            )

    @pytest.mark.xfail(reason=(
        "Auto-advance skips policy for coordination-only states; "
        "3M IR interleaves domain work with coordination (no explicit BUSINESS states)"
    ))
    def test_researcher_calls_tools(self):
        """Verify researcher events have write/research/revise/update tool calls."""
        result = self._run(fail_probability=0)
        researcher_tool_names = set()
        for event in result.trace:
            if event.agent.startswith("researcher"):
                for tc in event.tool_calls:
                    researcher_tool_names.add(tc.get("tool_name"))
        expected = {"write_section", "research_topic", "update_references"}
        assert expected.issubset(researcher_tool_names), (
            f"Missing researcher tools: {expected - researcher_tool_names}"
        )

    def test_backward_compat_no_policy(self):
        """Existing tests still pass with no policy (RandomPolicy default)."""
        result = run_ir(self.ir, seed=42, timeout=10)
        assert result.success
        assert result.final_states["editor"] == "ed_done"
        # tool_calls should be empty lists
        for event in result.trace:
            assert event.tool_calls == []

    @pytest.mark.xfail(reason=(
        "Auto-advance skips policy for coordination-only states; "
        "3M IR interleaves domain work with coordination (no explicit BUSINESS states)"
    ))
    def test_tool_count(self):
        """With fail_probability=0, verify the expected tool call pattern.

        Happy path (no flags, no revisions):
        - 3 researchers × (write_section + research_topic + update_references) = 9 tools
        - factchecker: 3 × fact_check = 3 tools
        - editor: 1 × review_sections = 1 tool
        Total = 13
        """
        result = self._run(fail_probability=0)
        all_tool_calls = [tc for e in result.trace for tc in e.tool_calls]
        # Count by tool name
        from collections import Counter
        counts = Counter(tc.get("tool_name") for tc in all_tool_calls)
        assert counts["write_section"] == 3
        assert counts["research_topic"] == 3
        assert counts["update_references"] == 3
        assert counts["fact_check"] == 3
        assert counts["review_sections"] == 1
        assert len(all_tool_calls) == 13
