"""IR v3 validator: schema validation + semantic checks (PlusCal pipeline).

Validates agents, resources, and channels only. Agent behavior is written
as PlusCal process bodies, not JSON states.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


_SCHEMA_PATH = Path(__file__).parent / "schema.json"
_SCHEMA = None


def _get_schema() -> dict:
    global _SCHEMA
    if _SCHEMA is None:
        with open(_SCHEMA_PATH) as f:
            _SCHEMA = json.load(f)
    return _SCHEMA


def _normalize_list(val) -> list[str]:
    """Normalize a string-or-list field to a list."""
    if isinstance(val, str):
        return [val]
    return list(val)


def _agent_id_to_const(agent_id: str) -> str:
    """Convert agent ID to PlusCal CONSTANT name (must match pluscal_generator)."""
    s = agent_id.replace("-", "_").replace(" ", "_")
    if not s:
        return "Agent"
    return s[0].upper() + s[1:]


def validate_ir(ir_data: dict) -> ValidationResult:
    """Validate IR v3 data against schema and semantic rules.

    Checks agents, resources, and channels. Does NOT validate states
    (behavior is written as PlusCal process bodies).
    """
    errors: list[str] = []

    # --- Schema validation ---
    schema = _get_schema()
    validator = jsonschema.Draft7Validator(schema)
    for error in validator.iter_errors(ir_data):
        path = ".".join(str(p) for p in error.absolute_path)
        errors.append(f"Schema: {error.message}" + (f" (at {path})" if path else ""))

    if errors:
        return ValidationResult(valid=False, errors=errors)

    # --- Semantic validation ---
    agent_ids = set()
    agent_consts: dict[str, str] = {}  # const_name -> agent_id (for collision check)
    for agent in ir_data.get("agents", []):
        aid = agent["id"]
        if aid in agent_ids:
            errors.append(f"Duplicate agent ID: {aid}")
        agent_ids.add(aid)

        # Check for constant name collisions
        const_name = _agent_id_to_const(aid)
        if const_name in agent_consts:
            errors.append(
                f"Agent '{aid}' and '{agent_consts[const_name]}' produce the same "
                f"TLA+ constant name '{const_name}'. Use more distinct agent IDs."
            )
        else:
            agent_consts[const_name] = aid

    resource_ids = set()
    for res in ir_data.get("resources", []):
        rid = res["id"]
        if rid in resource_ids:
            errors.append(f"Duplicate resource ID: {rid}")
        resource_ids.add(rid)
        if res["type"] == "Counter":
            config = res.get("config")
            if not config or "initial" not in config:
                errors.append(f"Counter resource '{rid}' must have config.initial defined")

    channel_ids = set()
    # Track (sender, receiver) pairs to enforce one channel per directed pair
    directed_pairs: dict[tuple[str, str], str] = {}
    for ch in ir_data.get("channels", []):
        cid = ch["id"]
        if cid in channel_ids:
            errors.append(f"Duplicate channel ID: {cid}")
        channel_ids.add(cid)
        ch_from = _normalize_list(ch["from"])
        ch_to = _normalize_list(ch["to"])
        for a in ch_from:
            if a not in agent_ids:
                errors.append(f"Channel '{cid}' from references unknown agent: {a}")
        for a in ch_to:
            if a not in agent_ids:
                errors.append(f"Channel '{cid}' to references unknown agent: {a}")
        # content_labels (optional, data-plane) must be a subset of labels
        bad_cl = [lbl for lbl in ch.get("content_labels", [])
                  if lbl not in ch.get("labels", [])]
        if bad_cl:
            errors.append(
                f"Channel '{cid}': content_labels {bad_cl} not in labels "
                f"{ch.get('labels', [])}")
        # Check duplicate (from, to) pairs
        for sender in ch_from:
            for receiver in ch_to:
                pair = (sender, receiver)
                if pair in directed_pairs:
                    errors.append(
                        f"Channel '{cid}': agents {sender}\u2192{receiver} already connected "
                        f"by channel '{directed_pairs[pair]}'. Use one channel per "
                        f"directed pair and distinguish messages with labels."
                    )
                else:
                    directed_pairs[pair] = cid

    return ValidationResult(valid=len(errors) == 0, errors=errors)
