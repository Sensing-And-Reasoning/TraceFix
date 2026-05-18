"""IR parsing and topology computation (pure functions, no I/O except load_ir)."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from tracefix.pipeline.pipeline.validator import ValidationResult, validate_ir


def _normalize_list(val) -> list[str]:
    if val is None:
        raise ValueError("Expected a string or list, got None")
    if isinstance(val, str):
        return [val]
    return list(val)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TopologyAgent:
    id: str
    initial_state: str
    tools: list[str] = field(default_factory=list)


@dataclass
class TopologyChannel:
    id: str
    from_agents: list[str]
    to_agents: list[str]
    labels: list[str] = field(default_factory=list)


@dataclass
class TopologyResource:
    id: str
    type: str  # "Lock" or "Counter"
    initial_value: int | None = None  # None for Lock, int for Counter


@dataclass
class ChannelOperation:
    """A single send or receive on a channel, from a specific state/action."""
    direction: str  # "send" or "receive"
    agent: str
    state: str
    target: str
    label: str | None = None


@dataclass
class StateMachine:
    agent_id: str
    states: list[str]
    initial_state: str
    terminal_states: list[str]
    decision_points: list[str]  # states with >1 action


@dataclass
class TopologyAnalysis:
    agent_count: int
    channel_count: int
    resource_count: int
    state_count: int
    decision_point_count: int
    communication_adjacency: dict[str, set[str]]  # agent_id → {connected agents}
    resource_usage: dict[str, set[str]]  # resource_id → {all agents that use it}
    resource_contention: dict[str, set[str]]  # resource_id → {competing agents, >1 only}


@dataclass
class Topology:
    agents: list[TopologyAgent]
    channels: list[TopologyChannel]
    resources: list[TopologyResource]
    state_machines: list[StateMachine]
    channel_whitelist: dict[str, dict[str, list[str]]]  # ch_id → {"from": [...], "to": [...]}
    channel_operations: dict[str, list[ChannelOperation]]  # ch_id → operations
    analysis: TopologyAnalysis


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_ir(path: str | Path) -> dict:
    """Read IR JSON from file, validate, and return the dict. Raises ValueError on invalid IR."""
    path = Path(path)
    with open(path) as f:
        ir = json.load(f)
    result: ValidationResult = validate_ir(ir)
    if not result.valid:
        raise ValueError(f"Invalid IR: {'; '.join(result.errors)}")
    return ir


def build_topology(ir: dict) -> Topology:
    """Pure function: compute full topology from a validated IR dict."""
    # --- Agents ---
    agents = [
        TopologyAgent(
            id=a["id"],
            initial_state=a["initial_state"],
            tools=a.get("tools", []),
        )
        for a in ir["agents"]
    ]

    # --- Channels (schema-level) ---
    channel_whitelist: dict[str, dict[str, list[str]]] = {}
    channels_raw: list[dict] = []
    for ch in ir["channels"]:
        from_agents = _normalize_list(ch["from"])
        to_agents = _normalize_list(ch["to"])
        channel_whitelist[ch["id"]] = {"from": from_agents, "to": to_agents}
        declared_labels = ch.get("labels", [])
        channels_raw.append({"id": ch["id"], "from": from_agents, "to": to_agents, "labels": declared_labels})

    # --- Resources ---
    resources = []
    for res in ir["resources"]:
        initial_value = None
        if res["type"] == "Counter":
            initial_value = res.get("config", {}).get("initial", 0)
        resources.append(TopologyResource(id=res["id"], type=res["type"], initial_value=initial_value))

    # --- Collect labels per channel from states ---
    channel_labels: dict[str, set[str]] = {ch["id"]: set() for ch in ir["channels"]}
    # --- Collect resource usage per agent ---
    resource_agents: dict[str, set[str]] = {res.id: set() for res in resources}
    # --- Collect channel operations ---
    channel_ops: dict[str, list[ChannelOperation]] = {ch["id"]: [] for ch in ir["channels"]}

    # --- State machines + label/resource/operation collection ---
    agent_states: dict[str, list[str]] = {a.id: [] for a in agents}
    agent_terminal: dict[str, list[str]] = {a.id: [] for a in agents}
    agent_decision: dict[str, list[str]] = {a.id: [] for a in agents}

    for state in ir["states"]:
        sid = state["id"]
        sagent = state["agent"]
        agent_states[sagent].append(sid)

        actions = state.get("actions", [])
        if len(actions) == 0:
            agent_terminal[sagent].append(sid)
        if len(actions) > 1:
            agent_decision[sagent].append(sid)

        for action in actions:
            target = action["target"]
            for send in action.get("send", []):
                ch = send["channel"]
                label = send.get("label")
                if ch in channel_labels:
                    if label:
                        channel_labels[ch].add(label)
                    channel_ops[ch].append(ChannelOperation(
                        direction="send", agent=sagent,
                        state=sid, target=target, label=label,
                    ))
            for recv in action.get("receive", []):
                ch = recv["channel"]
                label = recv.get("label")
                if ch in channel_labels:
                    if label:
                        channel_labels[ch].add(label)
                    channel_ops[ch].append(ChannelOperation(
                        direction="receive", agent=sagent,
                        state=sid, target=target, label=label,
                    ))
            for rid in action.get("acquire", []):
                if rid in resource_agents:
                    resource_agents[rid].add(sagent)
            for rid in action.get("release", []):
                if rid in resource_agents:
                    resource_agents[rid].add(sagent)

    # Build TopologyChannel — use declared labels if present, fallback to collected
    channels = [
        TopologyChannel(
            id=cr["id"],
            from_agents=cr["from"],
            to_agents=cr["to"],
            labels=sorted(cr["labels"]) if cr["labels"] else sorted(channel_labels.get(cr["id"], set())),
        )
        for cr in channels_raw
    ]

    # Build StateMachines
    state_machines = []
    for a in agents:
        sm = StateMachine(
            agent_id=a.id,
            states=agent_states[a.id],
            initial_state=a.initial_state,
            terminal_states=agent_terminal[a.id],
            decision_points=agent_decision[a.id],
        )
        state_machines.append(sm)

    # --- Analysis ---
    # Communication adjacency (bidirectional)
    adjacency: dict[str, set[str]] = {a.id: set() for a in agents}
    for ch in channels:
        for f in ch.from_agents:
            for t in ch.to_agents:
                if f != t:
                    adjacency[f].add(t)
                    adjacency[t].add(f)

    # Resource usage (all agents) and contention (>1 agent only)
    contention = {rid: agents_set for rid, agents_set in resource_agents.items() if len(agents_set) > 1}

    total_states = sum(len(sm.states) for sm in state_machines)
    total_decision = sum(len(sm.decision_points) for sm in state_machines)

    analysis = TopologyAnalysis(
        agent_count=len(agents),
        channel_count=len(channels),
        resource_count=len(resources),
        state_count=total_states,
        decision_point_count=total_decision,
        communication_adjacency=adjacency,
        resource_usage=resource_agents,
        resource_contention=contention,
    )

    return Topology(
        agents=agents,
        channels=channels,
        resources=resources,
        state_machines=state_machines,
        channel_whitelist=channel_whitelist,
        channel_operations=channel_ops,
        analysis=analysis,
    )
