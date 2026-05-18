"""Unit tests for runtime.topology."""

import json
import tempfile
from pathlib import Path

import pytest

from tracefix.runtime.enforcement.topology import build_topology, load_ir


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestNoChannels:
    def test_empty_channels(self):
        ir = {
            "agents": [{"id": "a", "initial_state": "s1"}, {"id": "b", "initial_state": "s2"}],
            "resources": [{"id": "lock", "type": "Lock"}],
            "channels": [],
            "states": [
                {"id": "s1", "agent": "a", "actions": [{"target": "s1_done", "acquire": ["lock"]}]},
                {"id": "s1_done", "agent": "a", "actions": [{"target": "s1_end", "release": ["lock"]}]},
                {"id": "s1_end", "agent": "a", "actions": []},
                {"id": "s2", "agent": "b", "actions": [{"target": "s2_done", "acquire": ["lock"]}]},
                {"id": "s2_done", "agent": "b", "actions": [{"target": "s2_end", "release": ["lock"]}]},
                {"id": "s2_end", "agent": "b", "actions": []},
            ],
        }
        topo = build_topology(ir)
        assert topo.channels == []
        assert topo.analysis.channel_count == 0
        # adjacency only from resource contention tracking (not in adjacency, that's channels only)
        assert topo.analysis.communication_adjacency == {"a": set(), "b": set()}
        assert topo.analysis.resource_contention == {"lock": {"a", "b"}}


class TestNoResources:
    def test_empty_resources(self):
        ir = {
            "agents": [{"id": "x", "initial_state": "x1"}, {"id": "y", "initial_state": "y1"}],
            "resources": [],
            "channels": [{"id": "ch", "from": "x", "to": "y"}],
            "states": [
                {"id": "x1", "agent": "x", "actions": [{"target": "x2", "send": [{"channel": "ch", "label": "msg"}]}]},
                {"id": "x2", "agent": "x", "actions": []},
                {"id": "y1", "agent": "y", "actions": [{"target": "y2", "receive": [{"channel": "ch", "label": "msg"}]}]},
                {"id": "y2", "agent": "y", "actions": []},
            ],
        }
        topo = build_topology(ir)
        assert topo.resources == []
        assert topo.analysis.resource_contention == {}
        assert topo.analysis.communication_adjacency == {"x": {"y"}, "y": {"x"}}


class TestInvalidIR:
    def test_missing_agents(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"resources": [], "channels": [], "states": []}, f)
            f.flush()
            with pytest.raises(ValueError, match="Invalid IR"):
                load_ir(f.name)

    def test_bad_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{bad json")
            f.flush()
            with pytest.raises(json.JSONDecodeError):
                load_ir(f.name)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_ir("/nonexistent/path.json")
