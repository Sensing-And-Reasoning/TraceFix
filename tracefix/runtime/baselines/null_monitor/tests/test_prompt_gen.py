"""Tests for tracefix.runtime.baselines.null_monitor prompt generation."""

import pytest

from tracefix.runtime.baselines.null_monitor.prompt_gen import generate_b2_prompt


# ---------------------------------------------------------------------------
# Fixture IR
# ---------------------------------------------------------------------------

FULL_IR = {
    "agents": [
        {"id": "builder_a"},
        {"id": "builder_b"},
        {"id": "reviewer"},
    ],
    "resources": [
        {"id": "build_lock", "type": "Lock"},
        {"id": "api_slots", "type": "Counter", "initial_value": 5},
    ],
    "channels": [
        {"id": "a_to_rev", "from": "builder_a", "to": "reviewer", "labels": ["submit", "update"]},
        {"id": "b_to_rev", "from": "builder_b", "to": "reviewer", "labels": ["submit"]},
        {"id": "rev_to_a", "from": "reviewer", "to": "builder_a", "labels": ["approve", "reject"]},
        {"id": "rev_to_b", "from": "reviewer", "to": "builder_b", "labels": ["approve", "reject"]},
    ],
}

MINIMAL_IR = {
    "agents": [{"id": "solo"}],
    "resources": [],
    "channels": [],
}

NO_RESOURCE_IR = {
    "agents": [{"id": "a"}, {"id": "b"}],
    "resources": [],
    "channels": [
        {"id": "ch_ab", "from": "a", "to": "b", "labels": ["ping"]},
    ],
}

NO_CHANNEL_IR = {
    "agents": [{"id": "a"}, {"id": "b"}],
    "resources": [{"id": "mutex", "type": "Lock"}],
    "channels": [],
}


# ---------------------------------------------------------------------------
# Basic output structure
# ---------------------------------------------------------------------------

class TestBasicStructure:
    def test_prompt_contains_agent_id(self):
        prompt = generate_b2_prompt("builder_a", "Build things.", FULL_IR)
        assert 'agent "builder_a"' in prompt

    def test_prompt_contains_task_description(self):
        prompt = generate_b2_prompt("builder_a", "Build things together.", FULL_IR)
        assert "Build things together." in prompt

    def test_prompt_contains_other_agents(self):
        prompt = generate_b2_prompt("builder_a", "Task.", FULL_IR)
        assert "builder_b" in prompt
        assert "reviewer" in prompt

    def test_prompt_contains_coordination_tools_section(self):
        prompt = generate_b2_prompt("builder_a", "Task.", FULL_IR)
        assert "acquire_lock" in prompt
        assert "release_lock" in prompt
        assert "send_message" in prompt
        assert "receive_message" in prompt
        assert "signal_done" in prompt

    def test_prompt_contains_guidelines(self):
        prompt = generate_b2_prompt("builder_a", "Task.", FULL_IR)
        assert "Guidelines" in prompt


# ---------------------------------------------------------------------------
# Channel assignment
# ---------------------------------------------------------------------------

class TestChannelAssignment:
    def test_send_channels_for_builder_a(self):
        prompt = generate_b2_prompt("builder_a", "Task.", FULL_IR)
        # builder_a can send on a_to_rev
        assert "a_to_rev" in prompt
        lines = prompt.split("\n")
        send_section = False
        for line in lines:
            if "SEND on" in line:
                send_section = True
            elif "RECEIVE on" in line:
                send_section = False
            if send_section and "a_to_rev" in line:
                assert "reviewer" in line
                assert "submit" in line

    def test_receive_channels_for_builder_a(self):
        prompt = generate_b2_prompt("builder_a", "Task.", FULL_IR)
        # builder_a receives on rev_to_a
        assert "rev_to_a" in prompt

    def test_reviewer_has_two_send_channels(self):
        prompt = generate_b2_prompt("reviewer", "Task.", FULL_IR)
        assert "rev_to_a" in prompt
        assert "rev_to_b" in prompt

    def test_reviewer_has_two_receive_channels(self):
        prompt = generate_b2_prompt("reviewer", "Task.", FULL_IR)
        assert "a_to_rev" in prompt
        assert "b_to_rev" in prompt

    def test_builder_b_send_and_receive(self):
        prompt = generate_b2_prompt("builder_b", "Task.", FULL_IR)
        assert "b_to_rev" in prompt  # send
        assert "rev_to_b" in prompt  # receive


# ---------------------------------------------------------------------------
# No channels
# ---------------------------------------------------------------------------

class TestNoChannels:
    def test_no_channels_shows_none(self):
        prompt = generate_b2_prompt("a", "Task.", NO_CHANNEL_IR)
        assert "(none)" in prompt


# ---------------------------------------------------------------------------
# No resources
# ---------------------------------------------------------------------------

class TestNoResources:
    def test_no_resources_shows_none(self):
        prompt = generate_b2_prompt("a", "Task.", NO_RESOURCE_IR)
        # The Resources section should show (none)
        lines = prompt.split("\n")
        resource_section = False
        found_none = False
        for line in lines:
            if line.strip().startswith("## Resources"):
                resource_section = True
            elif line.strip().startswith("##"):
                resource_section = False
            if resource_section and "(none)" in line:
                found_none = True
        assert found_none


# ---------------------------------------------------------------------------
# Resource formatting
# ---------------------------------------------------------------------------

class TestResourceFormatting:
    def test_lock_resource_format(self):
        prompt = generate_b2_prompt("builder_a", "Task.", FULL_IR)
        assert "build_lock" in prompt
        assert "Lock" in prompt
        assert "mutual exclusion" in prompt

    def test_counter_resource_format(self):
        prompt = generate_b2_prompt("builder_a", "Task.", FULL_IR)
        assert "api_slots" in prompt
        assert "Counter" in prompt
        assert "5 slots" in prompt


# ---------------------------------------------------------------------------
# Full topology
# ---------------------------------------------------------------------------

class TestFullTopology:
    def test_topology_section_present(self):
        prompt = generate_b2_prompt("builder_a", "Task.", FULL_IR)
        assert "Full Channel Topology" in prompt

    def test_topology_shows_all_channels(self):
        prompt = generate_b2_prompt("builder_a", "Task.", FULL_IR)
        assert "a_to_rev" in prompt
        assert "b_to_rev" in prompt
        assert "rev_to_a" in prompt
        assert "rev_to_b" in prompt


# ---------------------------------------------------------------------------
# Solo agent (minimal IR)
# ---------------------------------------------------------------------------

class TestSoloAgent:
    def test_solo_agent_no_other_agents(self):
        prompt = generate_b2_prompt("solo", "Do it alone.", MINIMAL_IR)
        assert "(none)" in prompt  # no other agents or channels

    def test_solo_agent_contains_id(self):
        prompt = generate_b2_prompt("solo", "Solo task.", MINIMAL_IR)
        assert 'agent "solo"' in prompt


# ---------------------------------------------------------------------------
# Label display in channels
# ---------------------------------------------------------------------------

class TestLabelDisplay:
    def test_labels_shown_in_send_channels(self):
        prompt = generate_b2_prompt("builder_a", "Task.", FULL_IR)
        # a_to_rev has labels submit, update
        assert "submit" in prompt
        assert "update" in prompt

    def test_labels_shown_in_topology(self):
        prompt = generate_b2_prompt("builder_a", "Task.", FULL_IR)
        assert "approve" in prompt
        assert "reject" in prompt
