"""Deterministic IR v3 → TLA+ spec + TLC config generator.

Optimized version with:
- Agent-specific Next formula (eliminates unnecessary guard evaluations)
- String messages instead of records (simpler state representation)
- Channel depth CONSTRAINT (bounds state space for large channel counts)
- Safety-only spec (no liveness, deadlock detected natively by TLC)
"""

from __future__ import annotations


def _normalize_list(val) -> list[str]:
    if isinstance(val, str):
        return [val]
    return list(val)


def _tla_str(s: str) -> str:
    """Wrap a string for TLA+ string literal."""
    return f'"{s}"'


def _sanitize_id(s: str) -> str:
    """Make an IR id safe for TLA+ identifier use (replace hyphens etc)."""
    return s.replace("-", "_").replace(" ", "_")


def generate_tla(ir_data: dict, *, channel_bound: int = 3) -> str:
    """Generate a complete TLA+ specification from IR v3 data.

    Args:
        ir_data: Validated IR v3 data.
        channel_bound: Max channel depth for CONSTRAINT operator (0 to disable).
    """
    agents = ir_data["agents"]
    resources = ir_data.get("resources", [])
    channels = ir_data.get("channels", [])
    states = ir_data["states"]

    locks = [r for r in resources if r["type"] == "Lock"]
    counters = [r for r in resources if r["type"] == "Counter"]

    # Build lookup maps
    state_map = {s["id"]: s for s in states}
    agent_states = {}
    for s in states:
        agent_states.setdefault(s["agent"], []).append(s)
    channel_map = {ch["id"]: ch for ch in channels}

    has_locks = len(locks) > 0
    has_counters = len(counters) > 0
    has_channels = len(channels) > 0

    lines = []

    def emit(s=""):
        lines.append(s)

    # Header
    emit("---- MODULE Protocol ----")
    emit("EXTENDS Sequences, Naturals, TLC")
    emit()

    # Constants
    const_parts = ["Agents"]
    if has_locks:
        const_parts.append("Locks")
    if has_counters:
        const_parts.append("Counters")
    if has_channels:
        const_parts.append("Channels")
    emit(f"CONSTANTS {', '.join(const_parts)}")
    emit()

    # Variables
    var_parts = ["pc"]
    if has_locks:
        var_parts.append("locks")
    if has_counters:
        var_parts.append("counters")
    if has_channels:
        var_parts.append("channels")
    emit(f"VARIABLES {', '.join(var_parts)}")
    emit()
    emit(f"vars == <<{', '.join(var_parts)}>>")
    emit()

    # Init
    emit("Init ==")
    # pc init: each agent starts at its initial_state
    pc_parts = []
    for agent in agents:
        pc_parts.append(f'{_tla_str(agent["id"])} :> {_tla_str(agent["initial_state"])}')
    emit(f"  /\\ pc = ({' @@ '.join(pc_parts)})")

    if has_locks:
        lock_parts = []
        for lock in locks:
            lock_parts.append(f'{_tla_str(lock["id"])} :> "FREE"')
        emit(f"  /\\ locks = ({' @@ '.join(lock_parts)})")

    if has_counters:
        counter_parts = []
        for counter in counters:
            initial = counter.get("config", {}).get("initial", 0)
            counter_parts.append(f'{_tla_str(counter["id"])} :> {initial}')
        emit(f"  /\\ counters = ({' @@ '.join(counter_parts)})")

    if has_channels:
        ch_parts = []
        for ch in channels:
            ch_parts.append(f'{_tla_str(ch["id"])} :> <<>>')
        emit(f"  /\\ channels = ({' @@ '.join(ch_parts)})")
    emit()

    # Generate TLA+ actions — track (action_name, agent_id) for agent-specific Next
    action_agent_pairs: list[tuple[str, str]] = []

    for state in states:
        sid = state["id"]
        sagent = state["agent"]
        actions = state.get("actions", [])

        if len(actions) == 0:
            # Terminal state: generate terminate action
            action_name = f"Terminate_{_sanitize_id(sid)}"
            action_agent_pairs.append((action_name, sagent))
            emit(f"{action_name}(agent) ==")
            emit(f"  /\\ pc[agent] = {_tla_str(sid)}")
            emit(f'  /\\ pc\' = [pc EXCEPT ![agent] = "done"]')
            unchanged = [v for v in var_parts if v != "pc"]
            if unchanged:
                emit(f"  /\\ UNCHANGED <<{', '.join(unchanged)}>>")
            emit()
        else:
            for ai, action in enumerate(actions):
                action_name = f"{_sanitize_id(sid)}_Act{ai}"
                action_agent_pairs.append((action_name, sagent))

                target = action["target"]
                sends = action.get("send", [])
                receives = action.get("receive", [])
                acquires = action.get("acquire", [])
                releases = action.get("release", [])

                emit(f"{action_name}(agent) ==")
                emit(f"  /\\ pc[agent] = {_tla_str(sid)}")

                # Guards
                for recv in receives:
                    ch = recv["channel"]
                    emit(f"  /\\ Len(channels[{_tla_str(ch)}]) > 0")
                    if "label" in recv:
                        emit(f"  /\\ Head(channels[{_tla_str(ch)}]) = {_tla_str(recv['label'])}")

                for rid in acquires:
                    if rid in [l["id"] for l in locks]:
                        emit(f"  /\\ locks[{_tla_str(rid)}] = \"FREE\"")
                    elif rid in [c["id"] for c in counters]:
                        emit(f"  /\\ counters[{_tla_str(rid)}] > 0")

                # pc update
                emit(f"  /\\ pc' = [pc EXCEPT ![agent] = {_tla_str(target)}]")

                # Determine what gets modified
                modified_vars = {"pc"}

                # Locks effects
                lock_excepts = []
                acquired_locks = [rid for rid in acquires if rid in [l["id"] for l in locks]]
                released_locks = [rid for rid in releases if rid in [l["id"] for l in locks]]

                for rid in acquired_locks:
                    if rid in released_locks:
                        # Net effect: release (acquire then release in same action)
                        lock_excepts.append(f"![{_tla_str(rid)}] = \"FREE\"")
                    else:
                        lock_excepts.append(f"![{_tla_str(rid)}] = agent")
                for rid in released_locks:
                    if rid not in acquired_locks:
                        lock_excepts.append(f"![{_tla_str(rid)}] = \"FREE\"")

                if lock_excepts and has_locks:
                    modified_vars.add("locks")
                    emit(f"  /\\ locks' = [locks EXCEPT {', '.join(lock_excepts)}]")

                # Counters effects
                counter_excepts = []
                acquired_counters = [rid for rid in acquires if rid in [c["id"] for c in counters]]
                released_counters = [rid for rid in releases if rid in [c["id"] for c in counters]]

                for rid in acquired_counters:
                    if rid in released_counters:
                        pass  # net zero
                    else:
                        counter_excepts.append(f"![{_tla_str(rid)}] = @ - 1")
                for rid in released_counters:
                    if rid not in acquired_counters:
                        counter_excepts.append(f"![{_tla_str(rid)}] = @ + 1")

                if counter_excepts and has_counters:
                    modified_vars.add("counters")
                    emit(f"  /\\ counters' = [counters EXCEPT {', '.join(counter_excepts)}]")

                # Channels effects: build a single channels' expression
                # We need to handle both receives (Tail) and sends (Append) on possibly
                # different channels, all in one EXCEPT expression.
                channel_excepts = []
                recv_channels = {}
                send_channels = {}

                for recv in receives:
                    ch = recv["channel"]
                    recv_channels[ch] = True
                for send in sends:
                    ch = send["channel"]
                    send_channels.setdefault(ch, []).append(send)

                # Channels that are both received from and sent to
                all_ch = set(list(recv_channels.keys()) + list(send_channels.keys()))
                for ch in sorted(all_ch):
                    if ch in recv_channels and ch in send_channels:
                        # Both consume and append on same channel
                        send_msgs = send_channels[ch]
                        expr = f"Tail(@)"
                        for s in send_msgs:
                            msg = _build_msg_record(s)
                            expr = f"Append({expr}, {msg})"
                        channel_excepts.append(f"![{_tla_str(ch)}] = {expr}")
                    elif ch in recv_channels:
                        channel_excepts.append(f"![{_tla_str(ch)}] = Tail(@)")
                    else:
                        send_msgs = send_channels[ch]
                        if len(send_msgs) == 1:
                            msg = _build_msg_record(send_msgs[0])
                            channel_excepts.append(f"![{_tla_str(ch)}] = Append(@, {msg})")
                        else:
                            # Multiple sends to same channel
                            expr = "@"
                            for s in send_msgs:
                                msg = _build_msg_record(s)
                                expr = f"Append({expr}, {msg})"
                            channel_excepts.append(f"![{_tla_str(ch)}] = {expr}")

                if channel_excepts and has_channels:
                    modified_vars.add("channels")
                    emit(f"  /\\ channels' = [channels EXCEPT {', '.join(channel_excepts)}]")

                # UNCHANGED
                unchanged = [v for v in var_parts if v not in modified_vars]
                if unchanged:
                    emit(f"  /\\ UNCHANGED <<{', '.join(unchanged)}>>")

                emit()

    # Terminated (defined before Next because Next references it)
    emit('Terminated == \\A a \\in Agents: pc[a] = "done"')
    emit()

    # Agent-specific Next: emit per-agent disjunctions instead of \E agent \in Agents
    # This eliminates guard evaluations for actions that can't fire for a given agent
    agent_actions: dict[str, list[str]] = {}
    for action_name, agent_id in action_agent_pairs:
        agent_actions.setdefault(agent_id, []).append(action_name)

    emit("Next ==")
    all_disjuncts = []
    for agent_id in [a["id"] for a in agents]:
        for action_name in agent_actions.get(agent_id, []):
            all_disjuncts.append(f"  {action_name}({_tla_str(agent_id)})")
    # Allow stuttering when all agents have terminated (prevents false deadlock reports)
    all_disjuncts.append("  (Terminated /\\ UNCHANGED vars)")
    emit("\n    \\/\n".join(all_disjuncts))
    emit()

    # Safety-only spec: no fairness constraints, no liveness properties.
    # Deadlock is checked natively by TLC (no -deadlock flag).
    # The Terminated stuttering clause in Next ensures terminal states
    # are not falsely reported as deadlocks.
    emit("Spec == Init /\\ [][Next]_vars")
    emit()

    # Invariants
    emit("TypeInvariant ==")
    all_state_ids = [s["id"] for s in states]
    emit(f"  /\\ \\A a \\in Agents: pc[a] \\in {{{', '.join(_tla_str(s) for s in all_state_ids)}, \"done\"}}")
    if has_locks:
        emit(f'  /\\ \\A r \\in Locks: locks[r] \\in Agents \\union {{"FREE"}}')
    if has_counters:
        emit("  /\\ \\A r \\in Counters: counters[r] \\in Nat")
    emit()

    # Note: MutualExclusion is not generated as an invariant because it is
    # structurally guaranteed by the lock model (locks[r] is a single value,
    # so two agents holding the same lock is impossible by construction).

    if has_locks:
        emit("NoOrphanLocks ==")
        emit('  Terminated => \\A r \\in Locks: locks[r] = "FREE"')
        emit()

    if has_channels:
        emit("ChannelsDrained ==")
        emit("  Terminated => \\A ch \\in Channels: Len(channels[ch]) = 0")
        emit()

    # Channel bound constraint (for TLC state space bounding)
    if has_channels and channel_bound > 0:
        emit(f"ChannelBound == \\A ch \\in DOMAIN channels: Len(channels[ch]) <= {channel_bound}")
        emit()

    emit("====")

    return "\n".join(lines)


def _build_msg_record(send: dict) -> str:
    """Build a TLA+ string literal for a message (not a record)."""
    if "label" in send:
        return _tla_str(send["label"])
    else:
        return '"msg"'


def generate_tlc_config(
    ir_data: dict,
    *,
    channel_bound: int = 3,
) -> str:
    """Generate TLC configuration file content (safety-only, no liveness).

    Args:
        ir_data: Validated IR v3 data.
        channel_bound: Max channel depth CONSTRAINT (0 to disable). Default 3.
    """
    agents = ir_data["agents"]
    resources = ir_data.get("resources", [])
    channels = ir_data.get("channels", [])

    locks = [r for r in resources if r["type"] == "Lock"]
    counters = [r for r in resources if r["type"] == "Counter"]

    has_locks = len(locks) > 0
    has_counters = len(counters) > 0
    has_channels = len(channels) > 0

    lines = []

    # Constants — only emit constants that the spec declares
    agent_set = ", ".join(f'"{a["id"]}"' for a in agents)
    lines.append(f"CONSTANTS")
    lines.append(f"  Agents = {{{agent_set}}}")

    if has_locks:
        lock_set = ", ".join(f'"{l["id"]}"' for l in locks)
        lines.append(f"  Locks = {{{lock_set}}}")

    if has_counters:
        counter_set = ", ".join(f'"{c["id"]}"' for c in counters)
        lines.append(f"  Counters = {{{counter_set}}}")

    if has_channels:
        ch_set = ", ".join(f'"{ch["id"]}"' for ch in channels)
        lines.append(f"  Channels = {{{ch_set}}}")

    lines.append("")
    lines.append("SPECIFICATION Spec")
    lines.append("")

    # Channel depth constraint — bounds state space for large channel counts
    if has_channels and channel_bound > 0:
        lines.append("CONSTRAINT ChannelBound")
        lines.append("")

    lines.append("INVARIANT TypeInvariant")
    if has_locks:
        lines.append("INVARIANT NoOrphanLocks")
    if has_channels:
        lines.append("INVARIANT ChannelsDrained")

    return "\n".join(lines)
