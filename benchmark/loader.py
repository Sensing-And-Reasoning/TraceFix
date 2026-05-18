"""Unified loader for benchmark tasks.

Merges patterns from protocolTasks/loader.py (scenario/difficulty metadata)
and protocolTasks_new/loader.py (checklist from environments/).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent
_TASKS_DIR = _BASE_DIR / "descriptions"
_ENV_DIR = _BASE_DIR / "environments"

_SCENARIO_MAP = {
    "1": "Shared Codebase Development",
    "2": "Smart Building",
    "3": "Research Writing",
    "4": "Code Collaboration",
    "5": "Medical Consultation",
    "6": "Codebase Development",
    "7": "Document Co-authoring",
    "8": "API System Development",
    "9": "Dining Philosophers",
    "10": "Parallel Build",
    "11": "Flexible Manufacturing",
    "12": "Collaborative Kitchen",
    "13": "Pharmaceutical Lab",
    "14": "Drug Discovery Pipeline",
    "15": "Semiconductor Fabrication",
    "16": "CI/CD Pipeline",
}

_DIFFICULTY_MAP = {"E": "Easy", "M": "Medium", "H": "Hard"}

_ID_RE = re.compile(r"^\d+[EMH]$")


@dataclass
class TaskEntry:
    task_id: str
    task_name: str
    scenario: str
    difficulty: str
    description: str
    checklist: list[dict] = field(default_factory=list)


def list_task_ids() -> list[str]:
    """Auto-discover task IDs from subdirectories matching ``\\d+[EMH]``."""
    ids = [
        d.name
        for d in _TASKS_DIR.iterdir()
        if d.is_dir() and _ID_RE.match(d.name)
    ]
    # Sort: numeric part first, then difficulty E<M<H
    diff_order = {"E": 0, "M": 1, "H": 2}
    ids.sort(key=lambda t: (int(t[:-1]), diff_order.get(t[-1], 9)))
    return ids


def load_task(task_id: str) -> TaskEntry:
    """Load a single task by ID (e.g. ``'3E'``, ``'12M'``).

    Raises ``ValueError`` if the task directory does not exist.
    """
    task_id = task_id.upper()
    task_dir = _TASKS_DIR / task_id
    if not task_dir.is_dir():
        available = ", ".join(list_task_ids())
        raise ValueError(f"Unknown task_id '{task_id}'. Available: {available}")

    desc_path = task_dir / "description.md"
    description = desc_path.read_text(encoding="utf-8")

    # Extract task name from first heading
    title_match = re.search(r"^#\s+(.+)$", description, re.MULTILINE)
    task_name = title_match.group(1).strip() if title_match else task_id
    # Strip "Task XY: " prefix if present
    task_name = re.sub(r"^Task\s+\w+:\s*", "", task_name)

    scenario_key = task_id[:-1]
    difficulty_key = task_id[-1]

    # Load checklist from environments/ (separate from agent-visible task files)
    checklist_path = _ENV_DIR / task_id / "checklist.json"
    checklist: list[dict] = []
    if checklist_path.exists():
        with open(checklist_path, encoding="utf-8") as f:
            checklist = json.load(f)

    return TaskEntry(
        task_id=task_id,
        task_name=task_name,
        scenario=_SCENARIO_MAP.get(scenario_key, "Unknown"),
        difficulty=_DIFFICULTY_MAP.get(difficulty_key, "Unknown"),
        description=description,
        checklist=checklist,
    )


def load_tasks(task_ids: list[str] | None = None) -> list[TaskEntry]:
    """Load multiple tasks. If *task_ids* is ``None``, loads all."""
    ids = [t.upper() for t in task_ids] if task_ids else list_task_ids()
    return [load_task(tid) for tid in ids]
