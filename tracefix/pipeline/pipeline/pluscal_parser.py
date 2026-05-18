"""Parse PlusCal source (embedded in TLA+ files) to extract IR v3 states array.

Uses tree-sitter-tlaplus to parse the PlusCal algorithm block directly,
preserving structural information that is lost in the PlusCal→TLA+ translation
(e.g. which variable a receive stores into, label scope boundaries).

Main entry point: ``parse_pluscal(tla_content, ir_data) -> ParseResult``
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import tree_sitter as ts
import tree_sitter_tlaplus

# Reuse shared types and post-processing from tla_parser
from tracefix.pipeline.pipeline.tla_parser import (
    IRMetadata,
    ParsedAction,
    ParseResult,
    build_ir_metadata,
    _action_to_dict,
    _merge_receive_dispatch,
    _infer_else_labels,
    _embed_inline_labels,
)


# ---------------------------------------------------------------------------
# Tree-sitter setup
# ---------------------------------------------------------------------------

_PARSER: ts.Parser | None = None


def _get_parser() -> ts.Parser:
    """Return a cached tree-sitter parser for TLA+/PlusCal."""
    global _PARSER
    if _PARSER is None:
        lang = ts.Language(tree_sitter_tlaplus.language())
        _PARSER = ts.Parser(lang)
    return _PARSER


# ---------------------------------------------------------------------------
# CST helpers
# ---------------------------------------------------------------------------

def _node_text(node: ts.Node, source: bytes) -> str:
    """Extract the text of a CST node."""
    return source[node.start_byte:node.end_byte].decode()


def _find_child(node: ts.Node, type_name: str) -> ts.Node | None:
    """Find first direct child of given type."""
    for c in node.children:
        if c.type == type_name:
            return c
    return None


def _find_children(node: ts.Node, type_name: str) -> list[ts.Node]:
    """Find all direct children of given type."""
    return [c for c in node.children if c.type == type_name]


def _find_descendant(node: ts.Node, type_name: str) -> ts.Node | None:
    """Find first descendant (DFS) of given type."""
    if node.type == type_name:
        return node
    for c in node.children:
        result = _find_descendant(c, type_name)
        if result is not None:
            return result
    return None


def _find_pcal_algorithm(tree: ts.Tree) -> ts.Node | None:
    """Find the pcal_algorithm node in a parsed TLA+ tree."""
    return _find_descendant(tree.root_node, "pcal_algorithm")


def _body_has_labels(node: ts.Node) -> bool:
    """Check if a pcal_algorithm_body contains label definitions."""
    children = node.children
    for i, c in enumerate(children):
        if c.type == "identifier" and i + 1 < len(children) and children[i + 1].type == ":":
            return True
    return False


# ---------------------------------------------------------------------------
# Data structures for label blocks
# ---------------------------------------------------------------------------

@dataclass
class LabelBlock:
    """A labeled segment of PlusCal code."""
    label: str
    stmts: list[ts.Node] = field(default_factory=list)
    while_label: str | None = None      # set to label name when this is a while entry
    while_guard: ts.Node | None = None   # the guard expression of the while
    scope_exit: str | None = None        # where the enclosing scope exits to
    fall_through: str | None = None      # computed: where this block falls through to


@dataclass
class StmtEffects:
    """Accumulated effects from interpreting a sequence of statements."""
    acquires: list[str] = field(default_factory=list)
    releases: list[str] = field(default_factory=list)
    sends: list[dict] = field(default_factory=list)
    receives: list[dict] = field(default_factory=list)
    gotos: list[str] = field(default_factory=list)
    increments: list[str] = field(default_factory=list)
    local_assigns: dict[str, object] = field(default_factory=dict)


@dataclass
class ProcessInfo:
    """Extracted info about one PlusCal process."""
    proc_name: str
    agent_id: str
    body: ts.Node
    local_vars: dict[str, object]


# ---------------------------------------------------------------------------
# Process extraction
# ---------------------------------------------------------------------------

def _extract_processes(algo: ts.Node, ir_data: dict, source: bytes) -> list[ProcessInfo]:
    """Extract process info from the pcal_algorithm node."""
    ir_agent_ids = {a["id"] for a in ir_data.get("agents", [])}
    processes = []

    for proc in _find_children(algo, "pcal_process"):
        proc_name = None
        for c in proc.children:
            if c.type == "identifier":
                proc_name = _node_text(c, source)
                break
        if proc_name is None:
            continue

        agent_id = _match_agent_id(proc_name, ir_agent_ids)

        local_vars = {}
        var_decls = _find_child(proc, "pcal_var_decls")
        if var_decls is not None:
            local_vars = _extract_local_vars(var_decls, source)

        body = _find_child(proc, "pcal_algorithm_body")
        if body is None:
            continue

        processes.append(ProcessInfo(
            proc_name=proc_name,
            agent_id=agent_id,
            body=body,
            local_vars=local_vars,
        ))

    return processes


def _match_agent_id(proc_name: str, ir_agent_ids: set[str]) -> str:
    """Match a process name (e.g. 'eic_proc') to an IR agent id."""
    candidate = re.sub(r"_proc$", "", proc_name)
    if candidate in ir_agent_ids:
        return candidate
    for aid in ir_agent_ids:
        if aid.lower() == candidate.lower():
            return aid
    return candidate


def _extract_local_vars(var_decls: ts.Node, source: bytes) -> dict[str, object]:
    """Extract local variable declarations from pcal_var_decls."""
    result = {}
    for decl in _find_children(var_decls, "pcal_var_decl"):
        ident = _find_child(decl, "identifier")
        if ident is None:
            continue
        name = _node_text(ident, source)
        value: object = None
        for c in decl.children:
            if c.type == "string":
                value = _node_text(c, source).strip('"')
            elif c.type == "boolean":
                value = _node_text(c, source)
            elif c.type == "nat_number":
                value = int(_node_text(c, source))
        result[name] = value
    return result


# ---------------------------------------------------------------------------
# Label block extraction (core algorithm)
# ---------------------------------------------------------------------------

def _walk_body_stmts(
    body: ts.Node,
    source: bytes,
    while_label: str | None = None,
    while_guard: ts.Node | None = None,
    scope_exit: str | None = None,
) -> list[LabelBlock]:
    """Recursively walk a pcal_algorithm_body, extracting LabelBlocks.

    Each block gets a `fall_through` set to the correct next label within
    its scope. The last block in the returned list gets `fall_through`
    set to `scope_exit`.
    """
    blocks: list[LabelBlock] = []
    current: LabelBlock | None = None
    children = list(body.children)

    i = 0
    while i < len(children):
        node = children[i]

        if node.type == "identifier":
            if i + 1 < len(children) and children[i + 1].type == ":":
                if current is not None:
                    blocks.append(current)
                label = _node_text(node, source)
                current = LabelBlock(
                    label=label,
                    while_label=while_label,
                    while_guard=while_guard,
                    scope_exit=scope_exit,
                )
                i += 2
                continue

        if node.type in ("{", "}", ";", "comment"):
            i += 1
            continue

        if current is None:
            i += 1
            continue

        if node.type == "pcal_while":
            guard = _get_while_guard(node)
            while_body = _find_child(node, "pcal_algorithm_body")
            if while_body is not None:
                after_while = _find_next_label(children, i + 1, source)
                if after_while is None:
                    after_while = scope_exit or "__done__"
                # Mark current as while-entry
                current.while_label = current.label
                current.while_guard = guard
                current.scope_exit = after_while
                # Recurse into while body: inner blocks loop back to while_label
                inner_blocks = _walk_body_stmts(
                    while_body, source,
                    while_label=current.label,
                    while_guard=guard,
                    scope_exit=current.label,  # last block in while body → loop back
                )
                blocks.append(current)
                blocks.extend(inner_blocks)
                current = None
            i += 1
            continue

        if node.type in ("pcal_if", "pcal_either"):
            if _control_has_internal_labels(node):
                # Flush current block with the control node as its last stmt
                current.stmts.append(node)
                # Set fall_through to the label AFTER the control structure
                after_control = _find_next_label(children, i + 1, source)
                if after_control is None:
                    after_control = scope_exit or "__done__"
                current.fall_through = after_control
                blocks.append(current)
                # Inner blocks exit to after_control too
                inner_blocks = _extract_control_inner_blocks(
                    node, source, while_label, while_guard, after_control,
                )
                blocks.extend(inner_blocks)
                current = None
            else:
                current.stmts.append(node)
            i += 1
            continue

        if node.type in ("pcal_macro_call", "pcal_skip", "pcal_assign", "pcal_goto",
                         "pcal_print", "pcal_assert", "pcal_await",
                         "pcal_with", "pcal_return"):
            current.stmts.append(node)
            i += 1
            continue

        i += 1

    if current is not None:
        blocks.append(current)

    # Set fall_through on each block, preserving values already set by recursion
    for idx, block in enumerate(blocks):
        if block.fall_through is not None:
            continue  # already set by recursive call (while body, either branch, etc.)
        if idx + 1 < len(blocks):
            block.fall_through = blocks[idx + 1].label
        else:
            block.fall_through = scope_exit or "__done__"

    return blocks


def _get_while_guard(while_node: ts.Node) -> ts.Node | None:
    """Extract the guard expression from a pcal_while node."""
    in_parens = False
    for c in while_node.children:
        if c.type == "(":
            in_parens = True
            continue
        if c.type == ")":
            break
        if in_parens:
            return c
    return None


def _find_next_label(children: list[ts.Node], start_idx: int, source: bytes) -> str | None:
    """Find the next label name in a children list starting from start_idx."""
    i = start_idx
    while i < len(children):
        if children[i].type == "identifier":
            if i + 1 < len(children) and children[i + 1].type == ":":
                return _node_text(children[i], source)
        i += 1
    return None


def _control_has_internal_labels(node: ts.Node) -> bool:
    """Check if a pcal_if or pcal_either has labels inside its branches (deep check).

    Recurses into nested control structures (pcal_if/pcal_either inside branch
    bodies) and chained else-if to find labels at any depth.
    """
    for body in _find_children(node, "pcal_algorithm_body"):
        if _body_has_labels(body):
            return True
        # Check nested control structures inside this body
        for stmt in body.children:
            if stmt.type in ("pcal_if", "pcal_either", "pcal_while"):
                if _control_has_internal_labels(stmt):
                    return True
    # Also check chained else-if (pcal_if children)
    for inner_if in _find_children(node, "pcal_if"):
        if _control_has_internal_labels(inner_if):
            return True
    return False


def _extract_control_inner_blocks(
    node: ts.Node,
    source: bytes,
    while_label: str | None,
    while_guard: ts.Node | None,
    scope_exit: str | None,
) -> list[LabelBlock]:
    """Extract LabelBlocks from branches of a pcal_if/pcal_either with internal labels."""
    blocks: list[LabelBlock] = []
    for branch_body in _find_children(node, "pcal_algorithm_body"):
        if _body_has_labels(branch_body):
            inner = _walk_body_stmts(
                branch_body, source,
                while_label=while_label,
                while_guard=while_guard,
                scope_exit=scope_exit,
            )
            blocks.extend(inner)
        else:
            # No direct labels; check nested control structures for labels
            for stmt in branch_body.children:
                if stmt.type in ("pcal_if", "pcal_either", "pcal_while"):
                    if _control_has_internal_labels(stmt):
                        blocks.extend(_extract_control_inner_blocks(
                            stmt, source, while_label, while_guard, scope_exit,
                        ))
    # Also recurse into chained else-if: pcal_if children (not pcal_algorithm_body)
    for inner_if in _find_children(node, "pcal_if"):
        blocks.extend(_extract_control_inner_blocks(
            inner_if, source, while_label, while_guard, scope_exit,
        ))
    return blocks


def _get_pre_label_stmts(body: ts.Node) -> list[ts.Node]:
    """Get statements BEFORE the first label in a body."""
    stmts: list[ts.Node] = []
    children = list(body.children)
    for i, c in enumerate(children):
        if c.type == "identifier" and i + 1 < len(children) and children[i + 1].type == ":":
            break  # reached first label
        if c.type not in ("{", "}", ";", "comment"):
            stmts.append(c)
    return stmts


def _get_first_label(body: ts.Node, source: bytes) -> str | None:
    """Get the first label name in a body, or None."""
    children = list(body.children)
    for i, c in enumerate(children):
        if c.type == "identifier" and i + 1 < len(children) and children[i + 1].type == ":":
            return _node_text(c, source)
    return None


# ---------------------------------------------------------------------------
# Statement interpretation
# ---------------------------------------------------------------------------

def _interpret_stmts(
    stmts: list[ts.Node],
    meta: IRMetadata,
    source: bytes,
    local_vars: dict[str, object],
) -> StmtEffects:
    """Interpret a list of PlusCal statements, extracting coordination effects."""
    effects = StmtEffects()
    for stmt in stmts:
        if stmt.type == "pcal_macro_call":
            _interpret_macro_call(stmt, meta, source, effects)
        elif stmt.type == "pcal_assign":
            _interpret_assign(stmt, source, effects, local_vars, meta)
        elif stmt.type == "pcal_goto":
            target = _find_child(stmt, "identifier")
            if target is not None:
                effects.gotos.append(_node_text(target, source))
        elif stmt.type == "pcal_skip":
            pass
        # pcal_if/pcal_either are NOT interpreted here — handled at action level
    return effects


def _interpret_macro_call(
    node: ts.Node,
    meta: IRMetadata,
    source: bytes,
    effects: StmtEffects,
) -> None:
    """Interpret a macro call, extracting coordination effects."""
    ident = _find_child(node, "identifier")
    if ident is None:
        return
    macro_name = _node_text(ident, source)
    args = _extract_macro_args(node, source)

    if macro_name == "send" and len(args) >= 2:
        ch_name = args[0]
        msg_label = args[1].strip('"')
        ch_id = meta.channel_vars.get(ch_name)
        if ch_id:
            effects.sends.append({"channel": ch_id, "label": msg_label})
    elif macro_name == "receive" and len(args) >= 2:
        ch_name = args[0]
        recv_var = args[1]
        ch_id = meta.channel_vars.get(ch_name)
        if ch_id:
            effects.receives.append({"channel": ch_id, "_recv_var": recv_var})
    elif macro_name == "acquire_lock" and len(args) >= 1:
        res_id = meta.lock_vars.get(args[0])
        if res_id:
            effects.acquires.append(res_id)
    elif macro_name == "release_lock" and len(args) >= 1:
        res_id = meta.lock_vars.get(args[0])
        if res_id:
            effects.releases.append(res_id)
    elif macro_name == "acquire_counter" and len(args) >= 1:
        res_id = meta.counter_vars.get(args[0])
        if res_id:
            effects.acquires.append(res_id)
    elif macro_name == "release_counter" and len(args) >= 1:
        res_id = meta.counter_vars.get(args[0])
        if res_id:
            effects.releases.append(res_id)


def _extract_macro_args(node: ts.Node, source: bytes) -> list[str]:
    """Extract arguments from a pcal_macro_call node."""
    args: list[str] = []
    in_args = False
    for c in node.children:
        if c.type == "(":
            in_args = True
            continue
        if c.type == ")":
            break
        if in_args and c.type != ",":
            args.append(_node_text(c, source))
    return args


def _interpret_assign(
    node: ts.Node,
    source: bytes,
    effects: StmtEffects,
    local_vars: dict[str, object],
    meta: IRMetadata,
) -> None:
    """Interpret an assignment, looking for variable increments."""
    lhs = _find_child(node, "pcal_lhs")
    if lhs is None:
        return
    var_name = _node_text(lhs, source)

    if var_name in meta.lock_vars or var_name in meta.counter_vars:
        return

    # Check RHS for increment pattern: var + 1
    rhs_nodes = []
    past_assign = False
    for c in node.children:
        if c.type == "assign":
            past_assign = True
            continue
        if past_assign:
            rhs_nodes.append(c)

    if len(rhs_nodes) == 1:
        rhs = rhs_nodes[0]
        if rhs.type == "bound_infix_op":
            children = [ch for ch in rhs.children if ch.type not in (",",)]
            if len(children) == 3:
                left = _node_text(children[0], source)
                op_node = children[1]
                right = _node_text(children[2], source)
                if left == var_name and op_node.type == "plus" and right == "1":
                    effects.increments.append(var_name)
                    return

    if var_name in local_vars:
        rhs_text = _node_text(rhs_nodes[0], source) if rhs_nodes else None
        effects.local_assigns[var_name] = rhs_text


# ---------------------------------------------------------------------------
# IF condition analysis
# ---------------------------------------------------------------------------

def _extract_if_condition_info(
    cond: ts.Node,
    source: bytes,
) -> tuple[str | None, str | None, dict | None]:
    """Extract label, cond_var, and guard from an IF/while condition.

    Returns (label, cond_var, guard).
    """
    if cond is None:
        return None, None, None

    if cond.type == "bound_infix_op":
        children = [c for c in cond.children if c.type not in (",",)]
        if len(children) == 3:
            left = children[0]
            op = children[1]
            right = children[2]

            if op.type == "eq":
                if left.type == "identifier_ref" and right.type == "string":
                    var_name = _node_text(left, source)
                    label = _node_text(right, source).strip('"')
                    return label, var_name, None
                if right.type == "identifier_ref" and left.type == "string":
                    var_name = _node_text(right, source)
                    label = _node_text(left, source).strip('"')
                    return label, var_name, None

            # Numeric comparison → loop guard
            if op.type in ("lt", "leq", "gt", "geq", "eq", "neq"):
                op_map = {"lt": "<", "leq": "<=", "gt": ">", "geq": ">=",
                          "eq": "=", "neq": "#"}
                op_str = op_map.get(op.type)
                if left.type == "identifier_ref" and right.type == "nat_number":
                    var_name = _node_text(left, source)
                    value = int(_node_text(right, source))
                    return None, None, {"var": var_name, "op": op_str, "value": value}
                if right.type == "identifier_ref" and left.type == "nat_number":
                    var_name = _node_text(right, source)
                    value = int(_node_text(left, source))
                    flip = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "=": "=", "#": "#"}
                    return None, None, {"var": var_name, "op": flip.get(op_str, op_str), "value": value}

    return None, None, None


def _is_always_true_guard(guard_node: ts.Node, source: bytes) -> bool:
    """Check if a while guard is trivially always TRUE."""
    if guard_node is None:
        return False
    text = _node_text(guard_node, source).strip()
    return text == "TRUE"


# ---------------------------------------------------------------------------
# Control flow → Actions conversion
# ---------------------------------------------------------------------------

def _effects_to_action(effects: StmtEffects, target: str) -> ParsedAction:
    """Convert StmtEffects to a ParsedAction with given target."""
    return ParsedAction(
        target=target,
        acquires=list(effects.acquires),
        releases=list(effects.releases),
        sends=list(effects.sends),
        receives=list(effects.receives),
        increments=list(effects.increments),
    )


def _merge_effects(base: StmtEffects, extra: StmtEffects) -> StmtEffects:
    """Merge two StmtEffects (base + extra)."""
    return StmtEffects(
        acquires=base.acquires + extra.acquires,
        releases=base.releases + extra.releases,
        sends=base.sends + extra.sends,
        receives=base.receives + extra.receives,
        gotos=base.gotos + extra.gotos,
        increments=base.increments + extra.increments,
        local_assigns={**base.local_assigns, **extra.local_assigns},
    )


def _block_to_actions(
    block: LabelBlock,
    next_label: str,
    meta: IRMetadata,
    source: bytes,
    local_vars: dict[str, object],
) -> list[ParsedAction]:
    """Convert a LabelBlock into one or more ParsedActions."""
    # Separate regular stmts from trailing control flow
    regular_stmts: list[ts.Node] = []
    control_node: ts.Node | None = None

    for stmt in block.stmts:
        if stmt.type in ("pcal_if", "pcal_either"):
            control_node = stmt
        else:
            regular_stmts.append(stmt)

    pre_effects = _interpret_stmts(regular_stmts, meta, source, local_vars)

    # Handle goto in regular statements
    if pre_effects.gotos and control_node is None:
        target = pre_effects.gotos[0]
        return [_effects_to_action(pre_effects, target)]

    # Handle while-entry blocks
    if block.while_guard is not None and block.while_label == block.label:
        return _while_entry_to_actions(block, next_label, pre_effects, meta, source, local_vars)

    # Handle control flow with internal labels (either/if that spawned inner blocks)
    if control_node is not None and _control_has_internal_labels(control_node):
        return _control_with_labels_to_actions(
            control_node, pre_effects, next_label, meta, source, local_vars,
        )

    # Handle non-label control flow
    if control_node is not None:
        if control_node.type == "pcal_if":
            return _if_to_actions(control_node, pre_effects, next_label, meta, source, local_vars)
        elif control_node.type == "pcal_either":
            return _either_to_actions(control_node, pre_effects, next_label, meta, source, local_vars)

    # Simple linear block
    return [_effects_to_action(pre_effects, next_label)]


def _while_entry_to_actions(
    block: LabelBlock,
    next_label: str,
    pre_effects: StmtEffects,
    meta: IRMetadata,
    source: bytes,
    local_vars: dict[str, object],
) -> list[ParsedAction]:
    """Handle a while-entry label: guard true → first body label, guard false → after-while."""
    exit_label = block.scope_exit or "__done__"

    # Check for always-true guard (while(TRUE)) → no false branch
    if _is_always_true_guard(block.while_guard, source):
        action = _effects_to_action(pre_effects, next_label)
        return [action]

    _, _, guard = _extract_if_condition_info(block.while_guard, source)

    true_action = _effects_to_action(pre_effects, next_label)
    true_action.guard = guard

    false_action = _effects_to_action(pre_effects, exit_label)

    return [true_action, false_action]


def _body_to_labeled_actions(
    body: ts.Node,
    pre_effects: StmtEffects,
    fall_through: str,
    meta: IRMetadata,
    source: bytes,
    local_vars: dict[str, object],
) -> list[ParsedAction]:
    """Convert a branch body into actions, handling nested control with deep labels.

    If the body has direct labels → interpret pre-label stmts, target = first label.
    If it has nested control with labels → expand the nested control.
    Otherwise → interpret all stmts.
    """
    first_label = _get_first_label(body, source)
    if first_label:
        pre_stmts = _get_pre_label_stmts(body)
        branch_effects = _interpret_stmts(pre_stmts, meta, source, local_vars)
        combined = _merge_effects(pre_effects, branch_effects)
        target = first_label
        if combined.gotos:
            target = combined.gotos[0]
        return [_effects_to_action(combined, target)]

    # No direct labels — check for nested control with deep labels
    stmts = _get_body_stmts(body)
    nested_control = None
    regular: list[ts.Node] = []
    for s in stmts:
        if s.type in ("pcal_if", "pcal_either") and nested_control is None:
            nested_control = s
        else:
            regular.append(s)

    if nested_control is not None and _control_has_internal_labels(nested_control):
        body_effects = _interpret_stmts(regular, meta, source, local_vars)
        combined = _merge_effects(pre_effects, body_effects)
        return _control_with_labels_to_actions(
            nested_control, combined, fall_through, meta, source, local_vars,
        )

    # Simple: interpret all stmts
    body_effects = _interpret_stmts(stmts, meta, source, local_vars)
    combined = _merge_effects(pre_effects, body_effects)
    target = combined.gotos[0] if combined.gotos else fall_through
    return [_effects_to_action(combined, target)]


def _control_with_labels_to_actions(
    control_node: ts.Node,
    pre_effects: StmtEffects,
    fall_through: str,
    meta: IRMetadata,
    source: bytes,
    local_vars: dict[str, object],
) -> list[ParsedAction]:
    """Handle either/if where branches contain internal labels.

    For each branch: interpret only pre-label stmts, target = first inner label.
    If a branch has no internal labels, target = fall_through.
    """
    actions: list[ParsedAction] = []

    if control_node.type == "pcal_either":
        for branch_body in _find_children(control_node, "pcal_algorithm_body"):
            branch_actions = _body_to_labeled_actions(
                branch_body, pre_effects, fall_through, meta, source, local_vars,
            )
            actions.extend(branch_actions)

    elif control_node.type == "pcal_if":
        bodies = _find_children(control_node, "pcal_algorithm_body")
        has_else = any(c.type == "else" for c in control_node.children)
        cond = _get_if_condition(control_node)
        label, cond_var, guard = _extract_if_condition_info(cond, source)

        # THEN branch
        if bodies:
            then_actions = _body_to_labeled_actions(
                bodies[0], pre_effects, fall_through, meta, source, local_vars,
            )
            # Annotate first action with condition info
            if then_actions:
                then_actions[0].label = label
                then_actions[0].cond_var = cond_var
                then_actions[0].guard = guard
            actions.extend(then_actions)

        # ELSE branch
        if has_else:
            # Check for chained else-if (else pcal_if as sibling)
            chained_if = None
            found_else = False
            for c in control_node.children:
                if c.type == "else":
                    found_else = True
                elif found_else and c.type == "pcal_if":
                    chained_if = c
                    break
                elif found_else:
                    break

            if chained_if is not None:
                # Chained else-if: recurse
                if _control_has_internal_labels(chained_if):
                    chained_actions = _control_with_labels_to_actions(
                        chained_if, pre_effects, fall_through, meta, source, local_vars,
                    )
                else:
                    chained_actions = _if_to_actions(
                        chained_if, pre_effects, fall_through, meta, source, local_vars,
                    )
                actions.extend(chained_actions)
            elif len(bodies) >= 2:
                else_actions = _body_to_labeled_actions(
                    bodies[1], pre_effects, fall_through, meta, source, local_vars,
                )
                actions.extend(else_actions)
        elif not has_else:
            # No else: false branch falls through
            actions.append(_effects_to_action(pre_effects, fall_through))

    return actions


def _if_to_actions(
    if_node: ts.Node,
    pre_effects: StmtEffects,
    fall_through: str,
    meta: IRMetadata,
    source: bytes,
    local_vars: dict[str, object],
) -> list[ParsedAction]:
    """Convert a pcal_if (without internal labels) into actions."""
    cond = _get_if_condition(if_node)
    label, cond_var, guard = _extract_if_condition_info(cond, source)

    bodies = _find_children(if_node, "pcal_algorithm_body")
    has_else = any(c.type == "else" for c in if_node.children)

    actions: list[ParsedAction] = []

    # THEN branch — use _branch_body_to_actions to handle nested control flow
    if bodies:
        then_actions = _branch_body_to_actions(
            bodies[0], pre_effects, fall_through, meta, source, local_vars,
        )
        if then_actions:
            then_actions[0].label = label
            then_actions[0].cond_var = cond_var
            then_actions[0].guard = guard
        actions.extend(then_actions)

    # ELSE branch
    if has_else:
        # Check for chained else-if: "else" followed directly by pcal_if (sibling)
        chained_if = None
        found_else = False
        for c in if_node.children:
            if c.type == "else":
                found_else = True
            elif found_else and c.type == "pcal_if":
                chained_if = c
                break
            elif found_else:
                break

        if chained_if is not None:
            # Chained if-else-if: recurse
            else_actions = _if_to_actions(chained_if, pre_effects, fall_through, meta, source, local_vars)
            actions.extend(else_actions)
        elif len(bodies) >= 2:
            else_actions = _branch_body_to_actions(
                bodies[1], pre_effects, fall_through, meta, source, local_vars,
            )
            actions.extend(else_actions)
    elif not has_else:
        # No else: false branch falls through
        actions.append(_effects_to_action(pre_effects, fall_through))

    return actions


def _either_to_actions(
    either_node: ts.Node,
    pre_effects: StmtEffects,
    fall_through: str,
    meta: IRMetadata,
    source: bytes,
    local_vars: dict[str, object],
) -> list[ParsedAction]:
    """Convert a pcal_either (without internal labels) into nondeterministic actions."""
    actions: list[ParsedAction] = []

    for branch_body in _find_children(either_node, "pcal_algorithm_body"):
        branch_actions = _branch_body_to_actions(
            branch_body, pre_effects, fall_through, meta, source, local_vars,
        )
        actions.extend(branch_actions)

    return actions


def _branch_body_to_actions(
    body: ts.Node,
    pre_effects: StmtEffects,
    fall_through: str,
    meta: IRMetadata,
    source: bytes,
    local_vars: dict[str, object],
) -> list[ParsedAction]:
    """Convert a branch body (from either/or or if/else) into actions.

    Handles inner pcal_if/pcal_either by separating regular stmts from control flow.
    """
    all_stmts = _get_body_stmts(body)

    # Separate regular stmts from control flow
    regular: list[ts.Node] = []
    control: ts.Node | None = None
    for s in all_stmts:
        if s.type in ("pcal_if", "pcal_either"):
            control = s
        else:
            regular.append(s)

    branch_effects = _interpret_stmts(regular, meta, source, local_vars)
    combined = _merge_effects(pre_effects, branch_effects)

    if control is not None:
        if control.type == "pcal_if":
            return _if_to_actions(control, combined, fall_through, meta, source, local_vars)
        elif control.type == "pcal_either":
            return _either_to_actions(control, combined, fall_through, meta, source, local_vars)

    target = combined.gotos[0] if combined.gotos else fall_through
    return [_effects_to_action(combined, target)]


def _get_if_condition(if_node: ts.Node) -> ts.Node | None:
    """Extract the condition expression from a pcal_if node."""
    in_parens = False
    for c in if_node.children:
        if c.type == "(":
            in_parens = True
            continue
        if c.type == ")":
            break
        if in_parens:
            return c
    return None


def _get_body_stmts(body: ts.Node) -> list[ts.Node]:
    """Get all statement nodes from a pcal_algorithm_body."""
    return [c for c in body.children
            if c.type not in ("{", "}", ";", "comment")]


# ---------------------------------------------------------------------------
# Assembly: blocks → states
# ---------------------------------------------------------------------------

def _assemble_states(
    processes: list[ProcessInfo],
    meta: IRMetadata,
    source: bytes,
) -> tuple[list[dict], dict[str, str], dict[str, dict]]:
    """Assemble parsed states from all processes.

    Returns (states, initial_states, local_variables).
    """
    all_states: list[dict] = []
    initial_states: dict[str, str] = {}
    local_variables: dict[str, dict] = {}

    for proc in processes:
        blocks = _walk_body_stmts(proc.body, source, scope_exit="__done__")
        if not blocks:
            continue

        initial_states[proc.agent_id] = blocks[0].label

        # Convert each block to a state using its fall_through as next_label
        for block in blocks:
            nl = block.fall_through or "__done__"
            actions = _block_to_actions(block, nl, meta, source, proc.local_vars)

            is_terminal = all(a.target == "__done__" for a in actions)
            has_effects = any(
                a.acquires or a.releases or a.sends or a.receives
                for a in actions
            )

            if is_terminal and not has_effects:
                all_states.append({
                    "id": block.label,
                    "agent": proc.agent_id,
                    "actions": [],
                })
            else:
                ir_actions = []
                for a in actions:
                    ad = _action_to_dict(a)
                    if a.target == "__done__" and "next_state" not in ad:
                        ad["next_state"] = "__done__"
                    if ad:
                        ir_actions.append(ad)
                all_states.append({
                    "id": block.label,
                    "agent": proc.agent_id,
                    "actions": ir_actions,
                })

        # Track local variables used in guards/increments
        for state in all_states:
            if state["agent"] != proc.agent_id:
                continue
            for action in state.get("actions", []):
                g = action.get("guard")
                if g:
                    var = g["var"]
                    if var in proc.local_vars:
                        local_variables[var] = {
                            "initial": proc.local_vars[var],
                            "agent": proc.agent_id,
                        }
                inc = action.get("increment")
                if inc:
                    items = inc if isinstance(inc, list) else [inc]
                    for v in items:
                        if v in proc.local_vars:
                            local_variables[v] = {
                                "initial": proc.local_vars[v],
                                "agent": proc.agent_id,
                            }

    return all_states, initial_states, local_variables


# ---------------------------------------------------------------------------
# Lint: adjacent acquire → release without intermediate work
# ---------------------------------------------------------------------------

def lint_adjacent_acquire_release(states: list[dict]) -> list[str]:
    """Check for acquire→release pairs with no intermediate work state.

    Operates on the extracted states list (same structure as states.json).
    Returns a list of warning strings for each violation found.
    """
    warnings: list[str] = []

    # Group states by agent
    agent_states: dict[str, dict[str, dict]] = {}
    for state in states:
        agent = state.get("agent", "")
        agent_states.setdefault(agent, {})[state["id"]] = state

    for agent, state_map in agent_states.items():
        for state_id, state in state_map.items():
            for action in state.get("actions", []):
                acquired = action.get("acquire")
                if not acquired:
                    continue
                acquired_set = set(acquired) if isinstance(acquired, list) else {acquired}

                next_id = action.get("next_state")
                if not next_id or next_id == "__done__" or next_id not in state_map:
                    continue

                next_state = state_map[next_id]
                next_actions = next_state.get("actions", [])
                if not next_actions:
                    continue

                # Check if ALL actions of the next state release overlapping
                # resources AND have no intermediate work (send/receive/guard/increment)
                all_release_only = True
                for na in next_actions:
                    released = na.get("release")
                    released_set = set(released) if isinstance(released, list) else ({released} if released else set())
                    overlap = acquired_set & released_set
                    if not overlap:
                        all_release_only = False
                        break
                    # Check for intermediate work indicators
                    if na.get("send") or na.get("receive") or na.get("guard") or na.get("increment"):
                        all_release_only = False
                        break

                if all_release_only:
                    warnings.append(
                        f"agent '{agent}': state '{state_id}' acquires "
                        f"{sorted(acquired_set)} and next state '{next_id}' "
                        f"releases immediately with no intermediate work label"
                    )

    return warnings


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_pluscal(tla_content: str, ir_data: dict) -> ParseResult:
    """Parse PlusCal source from a TLA+ file and extract IR v3 states array.

    Args:
        tla_content: Full content of Protocol_translated.tla (with PlusCal source)
        ir_data: Parsed ir.json (agents/resources/channels)

    Returns:
        ParseResult with states array, initial_states mapping, and any errors.
    """
    result = ParseResult()
    meta = build_ir_metadata(ir_data)
    source = tla_content.encode()

    parser = _get_parser()
    tree = parser.parse(source)

    algo = _find_pcal_algorithm(tree)
    if algo is None:
        result.errors.append("No PlusCal algorithm found in file")
        return result

    processes = _extract_processes(algo, ir_data, source)
    if not processes:
        result.errors.append("No PlusCal processes found")
        return result

    states, initial_states, local_variables = _assemble_states(processes, meta, source)

    result.initial_states = initial_states
    result.local_variables = local_variables

    # Merge receive → dispatch patterns
    states, merged_ids = _merge_receive_dispatch(states)
    result.merged_state_ids = merged_ids

    # Embed inline labels (same-block receive+if patterns)
    _embed_inline_labels(states)

    # Infer missing ELSE catch-all labels from IR channel labels
    _infer_else_labels(states, ir_data)

    # Strip internal fields
    for state in states:
        for action in state.get("actions", []):
            action.pop("_label", None)
            action.pop("_cond_var", None)
            recv = action.get("receive")
            if isinstance(recv, dict):
                recv.pop("_recv_var", None)

    result.states = states

    # Validation: check targets point to known states or __done__
    all_state_ids = {s["id"] for s in result.states}
    for state in result.states:
        for action in state.get("actions", []):
            target = action.get("next_state")
            if target and target != "__done__" and target not in all_state_ids:
                result.errors.append(
                    f"State '{state['id']}' has action targeting unknown state '{target}'"
                )

    # Validation: check resources/channels exist in IR
    ir_resource_ids = {r["id"] for r in ir_data.get("resources", [])}
    ir_channel_ids = {c["id"] for c in ir_data.get("channels", [])}
    for state in result.states:
        for action in state.get("actions", []):
            for field_name, valid_set in [("acquire", ir_resource_ids), ("release", ir_resource_ids)]:
                val = action.get(field_name)
                if val:
                    items = val if isinstance(val, list) else [val]
                    for item in items:
                        if item not in valid_set:
                            result.errors.append(
                                f"State '{state['id']}' references unknown resource '{item}'"
                            )
            for field_name in ("send", "receive"):
                val = action.get(field_name)
                if val:
                    items = val if isinstance(val, list) else [val]
                    for item in items:
                        ch = item.get("channel") if isinstance(item, dict) else None
                        if ch and ch not in ir_channel_ids:
                            result.errors.append(
                                f"State '{state['id']}' references unknown channel '{ch}'"
                            )

    return result
