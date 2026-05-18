"""Parse translated TLA+ (pcal.trans output) to extract IR v3 states array.

Given a Protocol_translated.tla file produced by the PlusCal translator and
the corresponding ir.json (agents/resources/channels, no states), this module
extracts the explicit state-machine information (states array) that the
PlusCal IR path is missing.

Main entry point: ``parse_translated_tla(tla_content, ir_data) -> ParseResult``
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class IRMetadata:
    """Lookup tables built from ir.json for variable identification."""
    lock_vars: dict[str, str] = field(default_factory=dict)       # tla_var -> resource_id
    counter_vars: dict[str, str] = field(default_factory=dict)    # tla_var -> resource_id
    channel_vars: dict[str, str] = field(default_factory=dict)    # tla_var -> channel_id
    agent_consts: dict[str, str] = field(default_factory=dict)    # TLA+ constant -> agent_id


@dataclass
class ParsedAction:
    """A single parsed action (one possible transition from a state)."""
    target: str
    acquires: list[str] = field(default_factory=list)
    releases: list[str] = field(default_factory=list)
    sends: list[dict] = field(default_factory=list)      # [{"channel": id, "label": msg}]
    receives: list[dict] = field(default_factory=list)    # [{"channel": id}]
    label: str | None = None                              # message label guard from IF dispatch
    guard: dict | None = None                             # loop guard: {"var", "op", "value"}
    increments: list[str] = field(default_factory=list)   # local vars incremented in this action
    cond_var: str | None = None                          # variable name from IF condition (e.g. "msg_r")


@dataclass
class ParseResult:
    """Result of parsing a translated TLA+ file."""
    states: list[dict] = field(default_factory=list)
    initial_states: dict[str, str] = field(default_factory=dict)  # agent_id -> initial state id
    errors: list[str] = field(default_factory=list)
    merged_state_ids: set[str] = field(default_factory=set)  # dispatch states merged away
    local_variables: dict[str, dict] = field(default_factory=dict)  # var -> {initial, agent}


# ---------------------------------------------------------------------------
# Step 0: Build IR metadata
# ---------------------------------------------------------------------------

def build_ir_metadata(ir_data: dict) -> IRMetadata:
    """Build lookup tables from ir.json for variable identification."""
    meta = IRMetadata()

    for res in ir_data.get("resources", []):
        rid = res["id"]
        rtype = res.get("type", "Lock")
        if rtype == "Lock":
            meta.lock_vars[rid] = rid
        elif rtype == "Counter":
            meta.counter_vars[rid] = rid

    for ch in ir_data.get("channels", []):
        cid = ch["id"]
        meta.channel_vars[cid] = cid

    # Build agent constant mapping: PlusCal uses CamelCase constants
    # e.g. agent id "builder_a" -> constant "Builder_a"
    # We'll populate this from the Init CASE block instead (more reliable)

    return meta


# ---------------------------------------------------------------------------
# Step 1: Structure extraction
# ---------------------------------------------------------------------------

def extract_translation_block(tla_content: str) -> str:
    """Extract the content between BEGIN TRANSLATION and END TRANSLATION markers."""
    m = re.search(
        r'\\\*\s*BEGIN TRANSLATION.*?\n(.*?)\\\*\s*END TRANSLATION',
        tla_content,
        re.DOTALL,
    )
    if not m:
        raise ValueError("No BEGIN/END TRANSLATION block found")
    return m.group(1)


def parse_init(block: str) -> dict[str, str]:
    """Parse Init to extract {TLA+ constant set -> initial label} mapping.

    Returns dict mapping constant name (e.g. "Builder_a") to initial label
    (e.g. "ba_acq_core").
    """
    # Find the pc = ... CASE block within Init
    # Pattern: pc = [self \in ProcSet |-> CASE self \in {Const} -> "label"
    #                                       [] self \in {Const2} -> "label2" ...]
    # The CASE block ends with ] at the end of a line (not the [] separators).
    # Use greedy match up to the last ] before a blank line or new /\ at column 0.
    init_match = re.search(
        r'/\\\s*pc\s*=\s*\[self\s*\\in\s*ProcSet\s*\|->\s*CASE\s*(.*?\])\s*$',
        block,
        re.DOTALL | re.MULTILINE,
    )
    if not init_match:
        return {}

    case_text = init_match.group(1)
    result = {}

    # Match each case arm: self \in {ConstName} -> "label"
    for m in re.finditer(
        r'self\s*\\in\s*\{(\w+)\}\s*->\s*"(\w+)"',
        case_text,
    ):
        const_name = m.group(1)
        label = m.group(2)
        result[const_name] = label

    return result


def _parse_local_var_inits(block: str) -> dict[str, dict]:
    """Extract local variable initial values from Init block.

    Matches: /\\ var = [self \\in {Constant} |-> value]
    Returns: {"var_name": {"initial": value, "process_constant": "Constant"}}
    """
    result = {}
    for m in re.finditer(
        r'/\\\s*(\w+)\s*=\s*\[self\s*\\in\s*\{(\w+)\}\s*\|->\s*(\w+|"[^"]*")\]',
        block,
    ):
        var_name = m.group(1)
        constant = m.group(2)
        raw_val = m.group(3)
        if raw_val.isdigit():
            val = int(raw_val)
        elif raw_val.startswith('"'):
            val = raw_val.strip('"')
        else:
            val = raw_val
        result[var_name] = {"initial": val, "process_constant": constant}
    return result


def parse_process_aggregations(block: str) -> dict[str, list[str]]:
    """Parse process aggregation operators to get label -> agent mapping.

    E.g. ``builder_a_proc(self) == ba_acq_core(self) \\/ ba_rel_core(self) ...``
    returns {"builder_a_proc": ["ba_acq_core", "ba_rel_core", ...]}
    """
    result: dict[str, list[str]] = {}

    # Process aggregations are single-line (possibly multi-line with continuation)
    # Pattern: name_proc(self) == label1(self) \/ label2(self) ...
    # They are NOT regular operators (no /\ pc[self] = ... guard)
    # Find them by: name(self) == word(self) \/ word(self) ...
    # where the body is purely disjunctions of label(self) calls

    # First, split the block into operator definitions
    operators = split_operators(block)

    for name, body in operators:
        # Check if this is a process aggregation: body is only label(self) \/ ...
        # Strip whitespace, the body should match: label(self) (\/ label(self))*
        stripped = body.strip()
        # A process aggregation body consists only of label(self) calls joined by \/
        labels = re.findall(r'(\w+)\(self\)', stripped)
        # Verify there's no /\ in the body (aggregations use only \/)
        if not labels or '/\\' in stripped:
            continue
        if '\\/' in stripped:
            # Multi-label process: label(self) \/ label(self) \/ ...
            result[name] = labels
        elif len(labels) == 1 and name.endswith('_proc'):
            # Single-label process: proc_name(self) == label(self)
            result[name] = labels

    return result


def split_operators(block: str) -> list[tuple[str, str]]:
    """Split translation block into individual operator definitions.

    Returns list of (name, body) tuples where name is the operator name
    and body is everything after ``name(self) ==``.
    Only returns operators that take ``(self)`` parameter.
    """
    # Find ALL operator definitions as boundaries (both with and without self)
    # name(self) == ...  OR  name == ...
    boundary_pattern = re.compile(
        r'^(\w+)(?:\(self\))?\s*==\s*',
        re.MULTILINE,
    )
    all_boundaries = list(boundary_pattern.finditer(block))

    # Find only the (self) operators — those are the ones we return
    self_pattern = re.compile(r'^(\w+)\(self\)\s*==\s*', re.MULTILINE)
    self_matches = list(self_pattern.finditer(block))

    if not self_matches:
        return []

    # Build a sorted list of all boundary start positions
    boundary_starts = sorted(m.start() for m in all_boundaries)

    results = []
    for m in self_matches:
        name = m.group(1)
        start = m.end()
        # Find the next boundary after this operator's start
        end = len(block)
        for bs in boundary_starts:
            if bs > m.start():
                end = bs
                break
        body = block[start:end].strip()
        results.append((name, body))

    return results


# ---------------------------------------------------------------------------
# Step 2: Operator parsing
# ---------------------------------------------------------------------------

def _extract_pc_guard(body: str) -> str | None:
    """Extract the pc guard state from an operator body."""
    m = re.search(r'pc\[self\]\s*=\s*"(\w+)"', body)
    return m.group(1) if m else None


def _extract_pc_targets(text: str) -> list[str]:
    """Extract all pc transition targets from text."""
    return re.findall(
        r'pc\'\s*=\s*\[pc\s+EXCEPT\s+!\[self\]\s*=\s*"(\w+)"\]',
        text,
    )


def _extract_lock_acquires(text: str, meta: IRMetadata) -> list[str]:
    """Find lock acquire patterns: lock = "FREE" /\\ lock' = self."""
    acquires = []
    for var in meta.lock_vars:
        # Guard: var = "FREE" and Effect: var' = self
        if re.search(rf'(?<!\w){re.escape(var)}\s*=\s*"FREE"', text) and \
           re.search(rf'(?<!\w){re.escape(var)}\'\s*=\s*self', text):
            acquires.append(meta.lock_vars[var])
    return acquires


def _extract_lock_releases(text: str, meta: IRMetadata) -> list[str]:
    """Find lock release patterns: lock' = "FREE"."""
    releases = []
    for var in meta.lock_vars:
        if re.search(rf'(?<!\w){re.escape(var)}\'\s*=\s*"FREE"', text):
            # Make sure this isn't also an acquire (guard: FREE + effect: self)
            if not re.search(rf'(?<!\w){re.escape(var)}\'\s*=\s*self', text):
                releases.append(meta.lock_vars[var])
    return releases


def _extract_counter_acquires(text: str, meta: IRMetadata) -> list[str]:
    """Find counter acquire patterns: counter > 0 /\\ counter' = counter - 1."""
    acquires = []
    for var in meta.counter_vars:
        if re.search(rf'(?<!\w){re.escape(var)}\s*>\s*0', text) and \
           re.search(rf'(?<!\w){re.escape(var)}\'\s*=\s*{re.escape(var)}\s*-\s*1', text):
            acquires.append(meta.counter_vars[var])
    return acquires


def _extract_counter_releases(text: str, meta: IRMetadata) -> list[str]:
    """Find counter release patterns: counter' = counter + 1."""
    releases = []
    for var in meta.counter_vars:
        if re.search(rf'(?<!\w){re.escape(var)}\'\s*=\s*{re.escape(var)}\s*\+\s*1', text):
            # Make sure this isn't also an acquire
            if not re.search(rf'(?<!\w){re.escape(var)}\s*>\s*0', text):
                releases.append(meta.counter_vars[var])
    return releases


def _extract_sends(text: str, meta: IRMetadata) -> list[dict]:
    """Find channel send patterns: ch' = Append(ch, "msg")."""
    sends = []
    for var in meta.channel_vars:
        for m in re.finditer(
            rf'(?<!\w){re.escape(var)}\'\s*=\s*Append\(\s*{re.escape(var)}\s*,\s*"([^"]+)"\s*\)',
            text,
        ):
            sends.append({
                "channel": meta.channel_vars[var],
                "label": m.group(1),
            })
    return sends


def _extract_receives(text: str, meta: IRMetadata) -> list[dict]:
    """Find channel receive patterns: Len(ch) > 0 + ch' = Tail(ch)."""
    receives = []
    for var in meta.channel_vars:
        if re.search(rf'Len\(\s*{re.escape(var)}\s*\)\s*>\s*0', text) and \
           re.search(rf'(?<!\w){re.escape(var)}\'\s*=\s*Tail\(\s*{re.escape(var)}\s*\)', text):
            # Extract the variable the message is stored in
            # Pattern: var' = [var EXCEPT ![self] = Head(ch)]
            head_m = re.search(
                rf"(\w+)'\s*=\s*\[\1\s+EXCEPT\s+!\[self\]\s*=\s*Head\(\s*{re.escape(var)}\s*\)\]",
                text,
            )
            recv_var = head_m.group(1) if head_m else None
            recv = {"channel": meta.channel_vars[var]}
            if recv_var:
                recv["_recv_var"] = recv_var
            receives.append(recv)
    return receives


def _build_action(text: str, meta: IRMetadata, target: str) -> ParsedAction:
    """Build a ParsedAction from a text block with a known target."""
    acquires = _extract_lock_acquires(text, meta) + _extract_counter_acquires(text, meta)
    releases = _extract_lock_releases(text, meta) + _extract_counter_releases(text, meta)
    sends = _extract_sends(text, meta)
    receives = _extract_receives(text, meta)
    increments = _extract_increments(text, meta)

    return ParsedAction(
        target=target,
        acquires=acquires,
        releases=releases,
        sends=sends,
        receives=receives,
        increments=increments,
    )


def _extract_msg_label(condition: str) -> str | None:
    """Extract message label from an IF condition like ``msg_[self] = "approved"``.

    Returns the string literal if the condition is a simple equality check
    of a process-local variable against a string, otherwise None (e.g. for
    boolean flag checks or numeric comparisons).
    """
    m = re.search(r'\w+\[self\]\s*=\s*"([^"]+)"', condition)
    return m.group(1) if m else None


def _extract_loop_guard(condition: str) -> dict | None:
    """Extract loop guard from IF condition like ``revDone[self] < 2``.

    Returns dict {"var": name, "op": op, "value": int} if condition is
    a numeric comparison on a process-local variable, else None.
    """
    m = re.search(r'(\w+)\[self\]\s*(<|<=|>|>=|=|#)\s*(\d+)', condition)
    if m:
        return {"var": m.group(1), "op": m.group(2), "value": int(m.group(3))}
    # Reverse form: 2 > var[self]
    m = re.search(r'(\d+)\s*(<|<=|>|>=|=|#)\s*(\w+)\[self\]', condition)
    if m:
        flip = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "=": "=", "#": "#"}
        return {"var": m.group(3), "op": flip[m.group(2)], "value": int(m.group(1))}
    return None


def _extract_increments(text: str, meta: IRMetadata) -> list[str]:
    """Extract local variable increments from operator text.

    Matches: var' = [var EXCEPT ![self] = var[self] + 1]
    Returns variable names that are incremented, excluding known IR resources.
    """
    pattern = r"(\w+)'\s*=\s*\[\1\s+EXCEPT\s+!\[self\]\s*=\s*\1\[self\]\s*\+\s*1\]"
    ir_vars = set(meta.lock_vars) | set(meta.counter_vars)
    return [m.group(1) for m in re.finditer(pattern, text) if m.group(1) not in ir_vars]


def _build_branch_action(branch_text: str, shared_text: str, meta: IRMetadata,
                         label: str | None = None,
                         guard: dict | None = None,
                         cond_var: str | None = None) -> ParsedAction:
    """Build a ParsedAction from one branch of an IF/THEN/ELSE."""
    full_text = branch_text + '\n' + shared_text
    targets = _extract_pc_targets(branch_text)
    if not targets:
        targets = _extract_pc_targets(shared_text)
    target = "__unknown__"
    if targets:
        target = "__done__" if targets[0] == "Done" else targets[0]
    action = _build_action(full_text, meta, target)
    action.label = label
    action.guard = guard
    action.cond_var = cond_var
    return action


def _build_branch_actions(branch_text: str, shared_text: str, meta: IRMetadata,
                          label: str | None = None,
                          guard: dict | None = None,
                          cond_var: str | None = None) -> list[ParsedAction]:
    """Build one or more ParsedActions from a branch that may contain \\/ disjuncts.

    If the branch text contains a top-level \\/ disjunction (e.g. an IF's ELSE
    branch with nondeterministic choice), split into separate actions.

    Handles indentation misalignment: when text comes from an inline regex
    capture (e.g. after ``ELSE``), the first line may lack the leading spaces
    that subsequent lines have, causing \\/ markers to appear at different
    columns. This is fixed by re-aligning the first line.
    """
    # Fix misaligned first line: when the first \/ is at a different column
    # than a subsequent \/, add spaces to the first line to align them.
    lines = branch_text.split('\n')
    if len(lines) > 1:
        first_disj = re.search(r'\\/', lines[0])
        if first_disj:
            for later_line in lines[1:]:
                later_disj = re.search(r'\\/', later_line)
                if later_disj:
                    offset = later_disj.start() - first_disj.start()
                    if offset > 0:
                        lines[0] = ' ' * offset + lines[0]
                        branch_text = '\n'.join(lines)
                    break

    disj = _split_disjuncts(branch_text)
    if disj:
        return [_build_branch_action(d, shared_text, meta, label, guard, cond_var) for d in disj]
    return [_build_branch_action(branch_text, shared_text, meta, label, guard, cond_var)]


def _split_disjuncts(body: str) -> list[str] | None:
    """Split a body with top-level \\/ disjunctions into branches.

    Returns None if no disjunction is found.
    Handles patterns like:
        /\\ \\/ /\\ effect1
           \\/ /\\ effect2
        /\\ shared_effect   (shared across branches)

    Uses line-by-line analysis: finds the \\/ column from the first
    occurrence, then classifies each line as branch-start, branch-cont,
    or shared (based on column position).
    """
    lines = body.split('\n')

    # Step 1: Find the \/ column (disjunction separator column)
    disj_col = None
    for line in lines:
        m = re.search(r'\\/', line)
        if m:
            disj_col = m.start()
            break

    if disj_col is None:
        return None

    # Step 2: Classify lines into regions: pre-disjunction, disjunction, post-disjunction
    # A line is part of the disjunction block if:
    #   - It has \/ at disj_col (branch separator), OR
    #   - It has /\ at a column > disj_col (branch continuation), OR
    #   - It's the /\ \/ intro line
    # Once inside the block, we leave when we see /\ at col <= disj_col
    # without \/ (i.e., a shared conjunct after the disjunction).

    pre_lines: list[str] = []
    disj_lines: list[str] = []
    post_lines: list[str] = []
    in_disj = False
    past_disj = False

    for line in lines:
        if past_disj:
            post_lines.append(line)
            continue

        # Check if this line has \/ at disj_col (branch separator)
        is_disj_sep = (
            len(line) > disj_col + 1
            and line[disj_col:disj_col + 2] == '\\/'
        )

        # Check if this line introduces the disjunction (/\ \/)
        is_disj_intro = bool(re.search(r'/\\\s*\\/', line)) and not in_disj

        if is_disj_intro or is_disj_sep:
            in_disj = True
            disj_lines.append(line)
        elif in_disj:
            # Check if still inside a branch
            m_conj = re.match(r'^(\s*)/\\', line)
            if m_conj:
                col = len(m_conj.group(1))
                if col > disj_col:
                    # Deeper indentation — still inside a branch
                    disj_lines.append(line)
                else:
                    # At or shallower than disj column — end of disjunction
                    in_disj = False
                    past_disj = True
                    post_lines.append(line)
            else:
                # Non-/\ line — check indentation
                stripped = line.lstrip()
                indent = len(line) - len(stripped)
                if indent > disj_col and stripped:
                    disj_lines.append(line)
                else:
                    in_disj = False
                    past_disj = True
                    post_lines.append(line)
        else:
            pre_lines.append(line)

    if not disj_lines:
        return None

    # Step 4: Split disjunction lines into branches at \/ markers
    branches: list[list[str]] = []
    current_branch: list[str] = []

    for line in disj_lines:
        is_sep = (
            len(line) > disj_col + 1
            and line[disj_col:disj_col + 2] == '\\/'
        )
        if is_sep:
            if current_branch:
                branches.append(current_branch)
            # Extract content after \/
            after = line[disj_col + 2:].strip()
            current_branch = [after] if after else []
        else:
            current_branch.append(line)

    if current_branch:
        branches.append(current_branch)

    if not branches:
        return None

    # Step 5: Combine each branch with shared (pre + post) lines
    shared_text = '\n'.join(pre_lines + post_lines)
    result = []
    for branch_lines in branches:
        branch_text = '\n'.join(branch_lines)
        combined = branch_text + '\n' + shared_text
        result.append(combined)

    return result


def _has_if_then_else(body: str) -> bool:
    """Check if the body contains an IF/THEN/ELSE pattern."""
    return bool(re.search(r'\bIF\b', body))


def _find_if_block_end(body: str, if_pos: int) -> int:
    """Find end of IF block using indentation of the preceding /\\ conjunct.

    The IF is always preceded by /\\ at some column. All content inside the
    IF block (THEN, ELSE, nested IFs) is indented deeper. The block ends
    when we encounter the next /\\ at the same column (or lower), or at
    end of body.
    """
    # Find the /\ column on the line containing IF
    line_start = body.rfind('\n', 0, if_pos) + 1
    prefix = body[line_start:if_pos]
    conj_m = re.search(r'/\\', prefix)
    conj_col = conj_m.start() if conj_m else 0

    # Scan lines after IF line, stop at first /\ at conj_col or lower
    pos = body.find('\n', if_pos)
    if pos == -1:
        return len(body)
    pos += 1  # start of next line

    while pos < len(body):
        next_nl = body.find('\n', pos)
        if next_nl == -1:
            next_nl = len(body)
        line = body[pos:next_nl]
        m = re.match(r'^(\s*)/\\', line)
        if m and len(m.group(1)) <= conj_col:
            return pos  # this /\ is at the same or outer level
        pos = next_nl + 1

    return len(body)


def _parse_if_then_else(body: str, meta: IRMetadata, state_id: str) -> list[ParsedAction]:
    """Parse an operator with IF/THEN/ELSE branching into multiple actions.

    Handles chained IF-ELSE-IF and extracts message labels from conditions.
    Uses indentation-aware block boundary detection to correctly handle
    nested IFs with multi-line THEN/ELSE blocks.
    """
    if_start = body.find('IF ')
    if if_start == -1:
        return []
    shared_before = body[:if_start]

    # Find IF block extent by indentation
    if_block_end = _find_if_block_end(body, if_start)
    if_block = body[if_start:if_block_end]
    shared_after = body[if_block_end:]

    # Match IF/THEN/ELSE within the delimited block
    # Use greedy (.*) for ELSE since block boundary is already known
    m = re.search(
        r'IF\s+(.+?)\n\s*THEN\s*(.*?)\n\s*ELSE\s*(.*)',
        if_block,
        re.DOTALL,
    )
    if not m:
        # Fallback: single-line IF
        m = re.search(
            r'IF\s+(.+?)\s+THEN\s*(.*?)\s+ELSE\s*(.*?)$',
            if_block,
            re.MULTILINE,
        )
    if not m:
        return []

    shared_text = shared_before + '\n' + shared_after

    return _parse_if_chain(m.group(1), m.group(2), m.group(3), shared_text, meta)


def _extract_trailing_shared(text: str) -> tuple[str, str]:
    """Extract shared conjuncts from the end of an ELSE text with nested IF.

    In TLA+ nested IF, lines after the IF/THEN/ELSE structure that have /\\
    at a column less than the THEN keyword's column are shared conjuncts
    (siblings of the IF block at the same conjunction level).

    Returns (shared_text, remaining_text).
    """
    lines = text.split('\n')

    # Find the THEN column
    then_col = None
    for line in lines:
        m = re.search(r'\bTHEN\b', line)
        if m:
            then_col = m.start()
            break

    if then_col is None:
        return '', text

    # Scan from end to find shared lines (shallower than THEN)
    shared_indices: set[int] = set()
    for i in range(len(lines) - 1, 0, -1):  # skip line 0
        line = lines[i]
        if not line.strip():
            continue
        m = re.match(r'^(\s*)/\\', line)
        if m and len(m.group(1)) < then_col:
            shared_indices.add(i)
        else:
            break  # stop at first non-shared line

    if not shared_indices:
        return '', text

    shared_lines = [lines[i] for i in sorted(shared_indices)]
    remaining_lines = [lines[i] for i in range(len(lines)) if i not in shared_indices]

    return '\n'.join(shared_lines), '\n'.join(remaining_lines)


def _parse_if_chain(condition_text: str, then_text: str, else_text: str,
                    shared_text: str, meta: IRMetadata) -> list[ParsedAction]:
    """Recursively parse IF/THEN/ELSE chain into actions with labels.

    When the ELSE block contains a nested IF, trailing lines at a shallower
    indentation than THEN (e.g. a shared pc' assignment) are extracted as
    ELSE-local shared text and combined with the outer shared_text.
    """
    label = _extract_msg_label(condition_text.strip())

    # Extract condition variable for variable-match check in merge pass
    cond_var = None
    if label is not None:
        cv_m = re.search(r'(\w+)\[self\]', condition_text.strip())
        if cv_m:
            cond_var = cv_m.group(1)

    # If not a message label, check for loop guard (while condition)
    guard = None
    if label is None:
        guard = _extract_loop_guard(condition_text.strip())

    else_stripped = else_text.strip()

    # Check for chained ELSE-IF
    if_pos = else_stripped.find('IF ')
    if if_pos != -1:
        # Extract shared conjuncts from the end of the ELSE text.
        # These are lines with /\ at a column shallower than THEN,
        # meaning they're siblings of the IF block (e.g. shared pc').
        trailing_shared, else_if_text = _extract_trailing_shared(else_stripped)
        combined_shared = shared_text + '\n' + trailing_shared

        nested = re.search(
            r'IF\s+(.+?)\n\s*THEN\s*(.*?)\n\s*ELSE\s*(.*)',
            else_if_text,
            re.DOTALL,
        )
        if not nested:
            nested = re.search(
                r'IF\s+(.+?)\s+THEN\s*(.*?)\s+ELSE\s*(.*?)$',
                else_if_text,
                re.MULTILINE,
            )

        if nested:
            # Use combined_shared for THEN too — the trailing shared text
            # (e.g. pc' = "di_loop") applies to ALL branches including THEN
            actions = _build_branch_actions(then_text.strip(), combined_shared, meta, label, guard=guard, cond_var=cond_var)
            # Chained: recurse into the nested IF with combined shared text
            actions.extend(_parse_if_chain(
                nested.group(1), nested.group(2), nested.group(3),
                combined_shared, meta,
            ))
        else:
            # Couldn't parse nested IF — treat entire ELSE as terminal
            actions = _build_branch_actions(then_text.strip(), shared_text, meta, label, guard=guard, cond_var=cond_var)
            actions.extend(_build_branch_actions(else_stripped, shared_text, meta))
    else:
        # Terminal ELSE branch (no label — default case)
        # Use _build_branch_actions to handle \/ disjuncts within branches
        actions = _build_branch_actions(then_text.strip(), shared_text, meta, label, guard=guard, cond_var=cond_var)
        actions.extend(_build_branch_actions(else_stripped, shared_text, meta))

    return actions


def parse_operator(name: str, body: str, meta: IRMetadata) -> list[ParsedAction]:
    """Parse a single operator into one or more ParsedActions.

    An operator with nondeterministic choice (\\/) or IF/THEN/ELSE
    produces multiple actions.
    """
    state_id = _extract_pc_guard(body)
    if state_id is None:
        return []  # Skip non-action operators (like process aggregations, Terminating, etc.)

    # Check for terminal state: pc' = "Done" with /\ TRUE body
    targets_all = _extract_pc_targets(body)
    if targets_all == ["Done"] and '/\\' in body:
        # Could be a simple Done transition or something with effects
        # Check if it's just TRUE + pc' = Done
        if re.search(r'/\\\s*TRUE', body):
            return [ParsedAction(target="__done__")]
        # If body has IF/THEN/ELSE or \/ branching, don't shortcut —
        # let the normal parsing below handle it so each branch becomes
        # a separate action (e.g. reply states with per-label sends).
        if not _has_if_then_else(body) and '\\/' not in body:
            # Has actual effects before Done (simple linear case)
            action = _build_action(body, meta, "__done__")
            return [action]
        # Fall through to IF / \/ parsing below

    # Determine which structural pattern appears first: IF or \/
    # When \/ comes before IF, the disjunction is top-level and branches
    # may contain nested IF. When IF comes first, the IF is top-level and
    # branches may contain nested \/.
    first_if = body.find('IF ')
    first_disj = body.find('\\/')
    if_before_disj = first_if != -1 and (first_disj == -1 or first_if < first_disj)

    # Check for IF/THEN/ELSE branching (only if IF appears before \/)
    if if_before_disj:
        actions = _parse_if_then_else(body, meta, state_id)
        if actions:
            return actions

    # Check for nondeterministic choice (\/)
    branches = _split_disjuncts(body)
    if branches:
        actions = []
        for branch_text in branches:
            # Check if this branch contains IF/THEN/ELSE
            if _has_if_then_else(branch_text):
                branch_actions = _parse_if_then_else(branch_text, meta, state_id)
                if branch_actions:
                    actions.extend(branch_actions)
                    continue
            branch_targets = _extract_pc_targets(branch_text)
            if branch_targets:
                target = branch_targets[0]
                if target == "Done":
                    actions.append(_build_action(branch_text, meta, "__done__"))
                else:
                    actions.append(_build_action(branch_text, meta, target))
        if actions:
            return actions

    # Fallback: try IF if we skipped it earlier (\/ came first but split failed)
    if not if_before_disj and first_if != -1:
        actions = _parse_if_then_else(body, meta, state_id)
        if actions:
            return actions

    # Simple linear operator: one action, one target
    if targets_all:
        target = targets_all[0]
        if target == "Done":
            action = _build_action(body, meta, "__done__")
            return [action]
        action = _build_action(body, meta, target)
        return [action]

    return []


# ---------------------------------------------------------------------------
# Step 3–4: Assembly
# ---------------------------------------------------------------------------

def _build_agent_map(
    aggregations: dict[str, list[str]],
    init_map: dict[str, str],
    ir_data: dict,
) -> dict[str, str]:
    """Build label -> agent_id mapping.

    Uses process aggregation names (e.g. builder_a_proc -> builder_a)
    and maps to IR agent ids.
    """
    label_to_agent: dict[str, str] = {}

    # Build constant -> agent_id mapping from Init + IR
    # Init gives us: {Constant -> initial_label}
    # Process aggregations give us: {proc_name -> [labels]}
    # We need: label -> agent_id

    # Step 1: Map proc_name -> agent_id
    # proc_name is like "builder_a_proc", agent_id is "builder_a"
    ir_agent_ids = {a["id"] for a in ir_data.get("agents", [])}

    proc_to_agent: dict[str, str] = {}
    for proc_name in aggregations:
        # Strip _proc suffix
        candidate = re.sub(r'_proc$', '', proc_name)
        if candidate in ir_agent_ids:
            proc_to_agent[proc_name] = candidate
        else:
            # Try matching by checking if any agent_id is a substring
            # or if lowercase matches
            for aid in ir_agent_ids:
                if aid.lower() == candidate.lower():
                    proc_to_agent[proc_name] = aid
                    break
            else:
                # Fallback: use the candidate as-is
                proc_to_agent[proc_name] = candidate

    # Step 2: Map label -> agent_id
    for proc_name, labels in aggregations.items():
        agent_id = proc_to_agent.get(proc_name, proc_name)
        for label in labels:
            label_to_agent[label] = agent_id

    return label_to_agent


def _action_to_dict(action: ParsedAction) -> dict:
    """Convert ParsedAction to IR v3 action dict."""
    d: dict = {}

    if action.target != "__done__":
        d["next_state"] = action.target

    if action.label:
        d["_label"] = action.label  # internal, consumed by merge pass

    if action.acquires:
        d["acquire"] = action.acquires if len(action.acquires) > 1 else action.acquires[0]
    if action.releases:
        d["release"] = action.releases if len(action.releases) > 1 else action.releases[0]
    if action.sends:
        if len(action.sends) == 1:
            d["send"] = action.sends[0]
        else:
            d["send"] = action.sends
    if action.receives:
        if len(action.receives) == 1:
            d["receive"] = action.receives[0]
        else:
            d["receive"] = action.receives

    if action.cond_var:
        d["_cond_var"] = action.cond_var

    if action.guard:
        d["guard"] = action.guard
    if action.increments:
        d["increment"] = action.increments if len(action.increments) > 1 else action.increments[0]

    return d


def _merge_receive_dispatch(states: list[dict]) -> list[dict]:
    """Merge receive→dispatch two-step patterns into single states.

    PlusCal translates ``receive(ch, var)`` without label filtering — it pops
    the queue head, then a subsequent IF state dispatches on the label.  This
    produces two states in the parsed IR:

        source:  action(s) with ``receive``, no other effects → target
        target:  2+ actions, at least one carrying ``_label``

    This pass folds the target's actions (with labels) back into the source,
    embedding the label inside each ``receive`` dict, and removes the target
    state entirely.

    Per-action merge criteria:
    - Action has ``receive``, no acquire/release/send
    - Target: 2+ actions, at least one has ``_label`` (internal field)
    - Target is only reached from this source state (in-degree == 1)
    - Variable match: ``_recv_var`` from receive must match ``_cond_var`` in
      target actions (prevents merging when dispatch checks a different var)

    Supports multi-action source states (e.g. nondeterministic receive from
    different channels, each with its own dispatch target).
    """
    from collections import defaultdict

    # Index: state_id → state dict
    state_idx: dict[str, dict] = {s["id"]: s for s in states}

    # Reverse index: target_id → set of source state ids (deduplicated)
    target_sources: dict[str, set[str]] = defaultdict(set)
    for state in states:
        for action in state.get("actions", []):
            t = action.get("next_state")
            if t:
                target_sources[t].add(state["id"])

    merged_targets: set[str] = set()  # target state ids to remove

    for state in states:
        actions = state.get("actions", [])
        new_actions = []
        any_merged = False

        for action in actions:
            # Check each action as a merge candidate
            if "receive" not in action:
                new_actions.append(action)
                continue
            if any(k in action for k in ("acquire", "release", "send")):
                new_actions.append(action)
                continue

            target_id = action.get("next_state")
            if not target_id or target_id not in state_idx:
                new_actions.append(action)
                continue

            target_state = state_idx[target_id]
            target_actions = target_state.get("actions", [])

            # Target needs 2+ actions with at least one _label
            if len(target_actions) < 2 or not any("_label" in ta for ta in target_actions):
                new_actions.append(action)
                continue

            # Target only reachable from this source (in-degree == 1)
            if len(target_sources.get(target_id, [])) != 1:
                new_actions.append(action)
                continue

            # Variable match: _recv_var must match _cond_var
            recv_var = action["receive"].get("_recv_var")
            if recv_var is not None:
                cond_vars = {ta.get("_cond_var") for ta in target_actions if "_cond_var" in ta}
                if cond_vars and recv_var not in cond_vars:
                    # Variable mismatch — don't merge
                    new_actions.append(action)
                    continue

            # Perform merge: copy receive into each target action
            receive_field = action["receive"]
            for ta in target_actions:
                merged = dict(ta)
                recv = dict(receive_field)
                lbl = merged.pop("_label", None)
                if lbl:
                    recv["label"] = lbl
                merged.pop("_cond_var", None)  # clean internal field
                merged["receive"] = recv
                new_actions.append(merged)

            merged_targets.add(target_id)
            any_merged = True

        if any_merged:
            state["actions"] = new_actions

    # Remove merged target states
    if merged_targets:
        states = [s for s in states if s["id"] not in merged_targets]

    return states, merged_targets


def _infer_else_labels(states: list[dict], ir_data: dict) -> int:
    """Infer missing receive labels for ELSE catch-all branches.

    When an IF/THEN/ELSE chain has N-1 explicit labels and the ELSE branch
    has no label, the missing label can be inferred by elimination from the
    IR channel's ``labels`` field.

    Groups receive actions by channel to support states with receives from
    multiple channels (e.g. after multi-action merge).

    Returns the number of labels inferred.
    """
    from collections import defaultdict

    # Build channel_id -> set of labels from IR
    channel_labels: dict[str, set[str]] = {}
    for ch in ir_data.get("channels", []):
        if ch.get("labels"):
            channel_labels[ch["id"]] = set(ch["labels"])

    inferred = 0

    for state in states:
        actions = state.get("actions", [])
        if len(actions) < 2:
            continue

        # Find actions with receive fields
        recv_actions = [a for a in actions if "receive" in a]
        if not recv_actions:
            continue

        # Group by channel
        channel_groups: dict[str, list[dict]] = defaultdict(list)
        for a in recv_actions:
            recv = a["receive"]
            ch = recv.get("channel") if isinstance(recv, dict) else None
            if ch:
                channel_groups[ch].append(a)

        for channel_id, group in channel_groups.items():
            if channel_id not in channel_labels:
                continue
            ir_labels_set = channel_labels[channel_id]

            existing: set[str] = set()
            unlabeled: list[dict] = []
            for a in group:
                recv = a["receive"]
                if isinstance(recv, dict) and recv.get("label"):
                    existing.add(recv["label"])
                else:
                    unlabeled.append(a)

            # If there are unlabeled actions and exactly one label is missing,
            # assign it to all unlabeled actions in this channel group
            if unlabeled and existing:
                missing = ir_labels_set - existing
                if len(missing) == 1:
                    label = missing.pop()
                    for a in unlabeled:
                        recv = a["receive"]
                        if isinstance(recv, dict):
                            recv["label"] = label
                            inferred += 1

    return inferred


def _embed_inline_labels(states: list[dict]) -> int:
    """Transfer _label from action to receive.label for same-state patterns.

    When a PlusCal label block contains both a receive and an IF dispatch on
    the received message, the parser produces actions with both a ``receive``
    dict and an ``_label`` internal field on the same action.  The merge pass
    (_merge_receive_dispatch) only handles the two-state pattern where receive
    and dispatch are in separate label blocks.

    This pass handles the single-state (inline) pattern by embedding _label
    directly into the receive dict before the strip pass removes it.

    Returns the number of labels embedded.
    """
    count = 0
    for state in states:
        for action in state.get("actions", []):
            label = action.get("_label")
            recv = action.get("receive")
            if label and recv and isinstance(recv, dict) and "label" not in recv:
                # Copy to avoid mutating shared dict references from
                # _effects_to_action (which shallow-copies the list but not
                # inner dicts).
                recv = dict(recv)
                action["receive"] = recv
                recv["label"] = label
                count += 1
    return count


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_translated_tla(tla_content: str, ir_data: dict) -> ParseResult:
    """Parse a translated TLA+ file and extract IR v3 states array.

    Args:
        tla_content: Full content of Protocol_translated.tla
        ir_data: Parsed ir.json (agents/resources/channels)

    Returns:
        ParseResult with states array, initial_states mapping, and any errors.
    """
    result = ParseResult()
    meta = build_ir_metadata(ir_data)

    try:
        block = extract_translation_block(tla_content)
    except ValueError as e:
        result.errors.append(str(e))
        return result

    # Parse Init for initial states
    init_map = parse_init(block)  # {Constant -> initial_label}

    # Parse local variable initial values from Init
    all_local_vars = _parse_local_var_inits(block)

    # Parse process aggregations for label -> agent mapping
    aggregations = parse_process_aggregations(block)

    # Build label -> agent_id mapping
    label_to_agent = _build_agent_map(aggregations, init_map, ir_data)

    # Split into operators and parse each
    operators = split_operators(block)

    # Collect parsed states
    states_dict: dict[str, dict] = {}  # state_id -> state dict

    for op_name, op_body in operators:
        # Skip non-action operators
        state_id = _extract_pc_guard(op_body)
        if state_id is None:
            continue

        actions = parse_operator(op_name, op_body, meta)
        if not actions:
            continue

        agent_id = label_to_agent.get(op_name, "__unknown__")

        # Check if all actions are terminal (__done__)
        is_terminal = all(a.target == "__done__" for a in actions)

        if is_terminal:
            # Terminal state with possible pre-done effects
            # Check if any action has actual effects
            has_effects = any(
                a.acquires or a.releases or a.sends or a.receives
                for a in actions
            )
            if has_effects:
                # Has effects before done — create state with actions targeting a synthetic done state
                ir_actions = []
                for a in actions:
                    ad = _action_to_dict(a)
                    ad["next_state"] = "__done__"
                    ir_actions.append(ad)
                states_dict[state_id] = {
                    "id": state_id,
                    "agent": agent_id,
                    "actions": ir_actions,
                }
            else:
                # Pure terminal state
                states_dict[state_id] = {
                    "id": state_id,
                    "agent": agent_id,
                    "actions": [],
                }
        else:
            ir_actions = []
            for a in actions:
                ad = _action_to_dict(a)
                # For mixed states (not all-terminal), __done__ actions produce
                # empty dicts since _action_to_dict omits next_state for them.
                # Explicitly add next_state so they're not dropped.
                if a.target == "__done__" and "next_state" not in ad:
                    ad["next_state"] = "__done__"
                if ad:
                    ir_actions.append(ad)
            states_dict[state_id] = {
                "id": state_id,
                "agent": agent_id,
                "actions": ir_actions,
            }

    # Build initial_states mapping: agent_id -> initial state id
    # Use init_map (Constant -> label) + agent constant mapping
    # We need to map constants to agent ids
    const_to_agent = _build_const_to_agent(init_map, aggregations, ir_data)
    for const_name, label in init_map.items():
        agent_id = const_to_agent.get(const_name)
        if agent_id:
            result.initial_states[agent_id] = label

    # Order states: group by agent, then by order of appearance in aggregation
    ordered_states = []
    seen = set()
    for proc_name, labels in aggregations.items():
        for label in labels:
            if label in states_dict and label not in seen:
                ordered_states.append(states_dict[label])
                seen.add(label)

    # Add any states not in aggregations (shouldn't happen, but be safe)
    for sid, state in states_dict.items():
        if sid not in seen:
            ordered_states.append(state)

    # Merge receive → dispatch patterns
    ordered_states, merged_ids = _merge_receive_dispatch(ordered_states)
    result.merged_state_ids = merged_ids

    # Embed inline labels (same-block receive+if patterns)
    _embed_inline_labels(ordered_states)

    # Infer missing ELSE catch-all labels from IR channel labels
    _infer_else_labels(ordered_states, ir_data)

    # Strip any remaining internal fields (non-merged dispatch states)
    for state in ordered_states:
        for action in state.get("actions", []):
            action.pop("_label", None)
            action.pop("_cond_var", None)
            recv = action.get("receive")
            if isinstance(recv, dict):
                recv.pop("_recv_var", None)

    result.states = ordered_states

    # Build local_variables: only vars referenced as guards or increments
    guard_vars: set[str] = set()
    for state in ordered_states:
        for action in state.get("actions", []):
            g = action.get("guard")
            if g:
                guard_vars.add(g["var"])
            inc = action.get("increment")
            if inc:
                items = inc if isinstance(inc, list) else [inc]
                guard_vars.update(items)

    for var_name in guard_vars:
        if var_name in all_local_vars:
            info = all_local_vars[var_name]
            agent_id = const_to_agent.get(info["process_constant"], "__unknown__")
            result.local_variables[var_name] = {
                "initial": info["initial"],
                "agent": agent_id,
            }

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


def _build_const_to_agent(
    init_map: dict[str, str],
    aggregations: dict[str, list[str]],
    ir_data: dict,
) -> dict[str, str]:
    """Build TLA+ constant -> agent_id mapping.

    Uses the initial labels from Init to match constants to process
    aggregations, then maps process names to IR agent ids.
    """
    ir_agent_ids = {a["id"] for a in ir_data.get("agents", [])}

    # Build label -> proc_name mapping
    label_to_proc: dict[str, str] = {}
    for proc_name, labels in aggregations.items():
        for label in labels:
            label_to_proc[label] = proc_name

    const_to_agent: dict[str, str] = {}
    for const_name, initial_label in init_map.items():
        proc_name = label_to_proc.get(initial_label)
        if proc_name:
            candidate = re.sub(r'_proc$', '', proc_name)
            if candidate in ir_agent_ids:
                const_to_agent[const_name] = candidate
            else:
                # Try case-insensitive match
                for aid in ir_agent_ids:
                    if aid.lower() == candidate.lower():
                        const_to_agent[const_name] = aid
                        break
                else:
                    const_to_agent[const_name] = candidate

    return const_to_agent
