"""Generate PlusCal scaffold from IR v3 data (agents/resources/channels only).

Produces a Protocol.tla with:
- MODULE header (EXTENDS Integers, Sequences, TLC)
- CONSTANTS: one per agent (capitalized)
- PlusCal algorithm block with:
  - variables: one per channel/lock/counter (individual, not maps)
  - macros: send, receive, acquire_lock, release_lock, acquire_counter, release_counter
  - process stubs: one per agent with skip placeholder
- Post-algorithm invariants: AllDone, TypeInvariant, NoOrphanLocks, ChannelsDrained, ChannelBound
"""

from __future__ import annotations


def _normalize_list(val) -> list[str]:
    if isinstance(val, str):
        return [val]
    return list(val)


def _agent_id_to_const(agent_id: str) -> str:
    """Convert agent ID to PlusCal CONSTANT name.

    Capitalizes first letter and sanitizes for TLA+ identifier use.
    Examples: coordinator -> Coordinator, workerA -> WorkerA, bank_a -> Bank_a
    """
    s = agent_id.replace("-", "_").replace(" ", "_")
    if not s:
        return "Agent"
    return s[0].upper() + s[1:]


def _sanitize_id(s: str) -> str:
    """Make an IR id safe for PlusCal variable name."""
    return s.replace("-", "_").replace(" ", "_")


def generate_pluscal_scaffold(ir_data: dict, *, channel_bound: int = 3, depth_bound: int = 0) -> str:
    """Generate a PlusCal scaffold Protocol.tla from IR data.

    The IR only needs agents, resources, and channels (no states).
    Process bodies contain skip placeholders for the LLM to fill in.

    Args:
        ir_data: IR v3 data with agents, resources, channels.
        channel_bound: Max channel depth for CONSTRAINT (default 3).
        depth_bound: Max BFS depth for CONSTRAINT via TLCGet("level") (0 to disable).

    Returns:
        Complete Protocol.tla content with PlusCal algorithm block.
    """
    agents = ir_data.get("agents", [])
    resources = ir_data.get("resources", [])
    channels = ir_data.get("channels", [])

    locks = [r for r in resources if r["type"] == "Lock"]
    counters = [r for r in resources if r["type"] == "Counter"]

    has_locks = len(locks) > 0
    has_counters = len(counters) > 0
    has_channels = len(channels) > 0

    # Build agent constant map: agent_id -> ConstantName
    agent_consts = {a["id"]: _agent_id_to_const(a["id"]) for a in agents}

    lines: list[str] = []

    def emit(s: str = "") -> None:
        lines.append(s)

    # --- Module header ---
    emit("---- MODULE Protocol ----")
    emit("EXTENDS Integers, Sequences, TLC")
    emit()

    # --- CONSTANTS: one per agent ---
    const_names = [agent_consts[a["id"]] for a in agents]
    emit("CONSTANTS " + ", ".join(const_names))
    emit()

    # --- PlusCal algorithm block ---
    emit("(* --algorithm Protocol {")

    # --- variables ---
    emit("variables")
    var_lines: list[str] = []

    # Channels: individual variables, each = <<>>
    for ch in channels:
        ch_var = _sanitize_id(ch["id"])
        ch_from = _normalize_list(ch["from"])
        ch_to = _normalize_list(ch["to"])
        labels = ch.get("labels", [])
        comment = f"\\* {','.join(ch_from)} -> {','.join(ch_to)}, labels: {labels}"
        var_lines.append(f"  {ch_var} = <<>>, {comment}")

    # Locks: individual variables, each = "FREE"
    for lock in locks:
        lock_var = _sanitize_id(lock["id"])
        var_lines.append(f'  {lock_var} = "FREE", \\* Lock')

    # Counters: individual variables, each = initial value
    for counter in counters:
        ctr_var = _sanitize_id(counter["id"])
        initial = counter.get("config", {}).get("initial", 0)
        var_lines.append(f"  {ctr_var} = {initial}, \\* Counter (non-negative)")

    # Join variables with semicolons (last one gets semicolon too)
    if var_lines:
        # Replace trailing comma on last variable with semicolon
        for i in range(len(var_lines) - 1):
            # Each line already ends with a comma after the value
            pass
        # Actually, PlusCal uses semicolons to separate variable declarations
        # Format: var = val; var2 = val2;
        # We need to fix the formatting
        formatted_vars: list[str] = []
        for v in var_lines:
            # Replace the comma after the value with a semicolon
            # The format is "  name = value, \* comment"
            # We want "  name = value; \* comment"
            formatted_vars.append(v.replace(",", ";", 1))
        for fv in formatted_vars:
            emit(fv)
    else:
        emit("  \\* No shared variables")

    emit()

    # --- Macros ---
    if has_channels:
        emit("macro send(ch, msg) {")
        emit("  ch := Append(ch, msg);")
        emit("}")
        emit()
        emit("macro receive(ch, var) {")
        emit("  await Len(ch) > 0;")
        emit("  var := Head(ch);")
        emit("  ch := Tail(ch);")
        emit("}")
        emit()

    if has_locks:
        emit("macro acquire_lock(lock) {")
        emit('  await lock = "FREE";')
        emit("  lock := self;")
        emit("}")
        emit()
        emit("macro release_lock(lock) {")
        emit('  lock := "FREE";')
        emit("}")
        emit()

    if has_counters:
        emit("macro acquire_counter(ctr) {")
        emit("  await ctr > 0;")
        emit("  ctr := ctr - 1;")
        emit("}")
        emit()
        emit("macro release_counter(ctr) {")
        emit("  ctr := ctr + 1;")
        emit("}")
        emit()

    # --- Process stubs ---
    for agent in agents:
        aid = agent["id"]
        const_name = agent_consts[aid]
        proc_name = _sanitize_id(aid) + "_proc"
        label_prefix = _sanitize_id(aid)

        emit(f"fair process ({proc_name} \\in {{{const_name}}})")
        emit('variables msg = "";')
        emit("{")
        emit(f"  {label_prefix}_start:")
        emit(f"    skip; \\* TODO: replace with {aid}'s protocol logic")
        # Explicit terminal label so every agent has a clean terminal state in
        # states.json. Fill in _start's body above and end by reaching _done
        # (fall through or `goto {label_prefix}_done`).
        emit(f"  {label_prefix}_done:")
        emit("    skip;")
        emit("}")
        emit()

    # Close algorithm block
    emit("} *)")
    emit()

    # --- Post-algorithm definitions ---
    # AllDone
    agent_const_set = ", ".join(const_names)
    emit(f"AllDone == \\A p \\in {{{agent_const_set}}}: pc[p] = \"Done\"")
    emit()

    # TypeInvariant
    emit("TypeInvariant ==")
    type_parts: list[str] = []
    # pc range: each agent process can be at any label or "Done"
    type_parts.append(f"  /\\ \\A p \\in {{{agent_const_set}}}: pc[p] \\in STRING")
    if has_locks:
        for lock in locks:
            lock_var = _sanitize_id(lock["id"])
            type_parts.append(
                f"  /\\ {lock_var} \\in {{{agent_const_set}, \"FREE\"}}"
            )
    if has_counters:
        for counter in counters:
            ctr_var = _sanitize_id(counter["id"])
            type_parts.append(f"  /\\ {ctr_var} \\in Nat")
    if has_channels:
        for ch in channels:
            ch_var = _sanitize_id(ch["id"])
            type_parts.append(f"  /\\ {ch_var} \\in Seq(STRING)")
    emit("\n".join(type_parts))
    emit()

    # NoOrphanLocks
    if has_locks:
        emit("NoOrphanLocks ==")
        lock_checks = []
        for lock in locks:
            lock_var = _sanitize_id(lock["id"])
            lock_checks.append(f'{lock_var} = "FREE"')
        emit(f"  AllDone => ({' /\\ '.join(lock_checks)})")
        emit()

    # ChannelsDrained
    if has_channels:
        emit("ChannelsDrained ==")
        ch_checks = []
        for ch in channels:
            ch_var = _sanitize_id(ch["id"])
            ch_checks.append(f"Len({ch_var}) = 0")
        emit(f"  AllDone => ({' /\\ '.join(ch_checks)})")
        emit()

    # ChannelBound
    if has_channels and channel_bound > 0:
        emit("ChannelBound ==")
        bound_checks = []
        for ch in channels:
            ch_var = _sanitize_id(ch["id"])
            bound_checks.append(f"Len({ch_var}) <= {channel_bound}")
        emit(f"  {' /\\ '.join(bound_checks)}")
        emit()

    # DepthBound
    if depth_bound > 0:
        emit(f"DepthBound == TLCGet(\"level\") < {depth_bound}")
        emit()

    emit("====")

    return "\n".join(lines)


def generate_tlc_config(ir_data: dict, *, channel_bound: int = 3, depth_bound: int = 0) -> str:
    """Generate TLC configuration file for PlusCal-based Protocol.tla.

    Args:
        ir_data: IR v3 data with agents, resources, channels.
        channel_bound: Max channel depth CONSTRAINT (default 3).
        depth_bound: Max BFS depth CONSTRAINT via TLCGet("level") (0 to disable).

    Returns:
        Protocol.cfg content.
    """
    agents = ir_data.get("agents", [])
    channels = ir_data.get("channels", [])

    locks = [r for r in ir_data.get("resources", []) if r["type"] == "Lock"]
    counters = [r for r in ir_data.get("resources", []) if r["type"] == "Counter"]

    has_locks = len(locks) > 0
    has_channels = len(channels) > 0

    lines: list[str] = []

    # CONSTANTS: AgentConst = "agent_id" for each agent
    lines.append("CONSTANTS")
    for agent in agents:
        const_name = _agent_id_to_const(agent["id"])
        lines.append(f'  {const_name} = "{agent["id"]}"')

    lines.append("")
    lines.append("SPECIFICATION Spec")
    lines.append("")

    # CONSTRAINT
    constraints: list[str] = []
    if has_channels and channel_bound > 0:
        constraints.append("CONSTRAINT ChannelBound")
    if depth_bound > 0:
        constraints.append("CONSTRAINT DepthBound")
    if constraints:
        lines.extend(constraints)
        lines.append("")

    # INVARIANTS
    lines.append("INVARIANT TypeInvariant")
    if has_locks:
        lines.append("INVARIANT NoOrphanLocks")
    if has_channels:
        lines.append("INVARIANT ChannelsDrained")

    return "\n".join(lines)
