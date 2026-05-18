"""Flexible manufacturing simulation config for task 11E."""

import json
from pathlib import Path

from benchmark.tools.sim_manufacturing import (
    CollectReportsStep,
    JobStep,
    ManufacturingSim,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "11E" / "metadata.json").read_text()
)

_JOB_STEPS = [
    JobStep(agent_id="TECHNICIAN_A", job_id="lathe_job_a"),
    JobStep(agent_id="TECHNICIAN_A", job_id="mill_job_a"),
    JobStep(agent_id="TECHNICIAN_B", job_id="lathe_job_b"),
    JobStep(agent_id="TECHNICIAN_B", job_id="mill_job_b"),
]

_COLLECT_REPORTS_STEPS = [
    CollectReportsStep(agent_id="SUPERVISOR", scope="all_jobs"),
]


class TwoTechnicianWorkshopSim(ManufacturingSim):
    """11E: Two technicians completing jobs on two workstations (lathe and
    mill) with a supervisor collecting completion reports."""

    # 11E has no inspect_quality tool — override inherited _DECISION_TOOLS.
    _DECISION_TOOLS: dict = {}

    def __init__(self) -> None:
        super().__init__(
            job_steps=_JOB_STEPS,
            collect_reports_steps=_COLLECT_REPORTS_STEPS,
            resources=["LATHE", "MILL"],
        )
        self.load_from_metadata(_METADATA)
