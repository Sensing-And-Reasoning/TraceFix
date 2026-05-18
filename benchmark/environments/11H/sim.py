"""Flexible manufacturing simulation config for task 11H."""

import json
from pathlib import Path

from benchmark.tools.sim_manufacturing import (
    InspectStep,
    JobStep,
    ManufacturingSim,
    PackageStep,
    ReplenishStep,
    ReworkStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "11H" / "metadata.json").read_text()
)

_JOB_STEPS = [
    JobStep(agent_id="WORKER_A", job_id="job_a1"),
    JobStep(agent_id="WORKER_A", job_id="job_a2"),
    JobStep(agent_id="WORKER_B", job_id="job_b1"),
    JobStep(agent_id="WORKER_B", job_id="job_b2"),
    JobStep(agent_id="WORKER_C", job_id="job_c1"),
    JobStep(agent_id="WORKER_C", job_id="job_c2"),
    JobStep(agent_id="WORKER_D", job_id="job_d1"),
    JobStep(agent_id="WORKER_D", job_id="job_d2"),
]

_INSPECT_STEPS = [
    InspectStep(agent_id="INSPECTOR", job_id="job_a1"),
    InspectStep(agent_id="INSPECTOR", job_id="job_a2"),
    InspectStep(agent_id="INSPECTOR", job_id="job_b1"),
    InspectStep(agent_id="INSPECTOR", job_id="job_b2"),
    InspectStep(agent_id="INSPECTOR", job_id="job_c1"),
    InspectStep(agent_id="INSPECTOR", job_id="job_c2"),
    InspectStep(agent_id="INSPECTOR", job_id="job_d1"),
    InspectStep(agent_id="INSPECTOR", job_id="job_d2"),
]

_REPLENISH_STEPS = [
    ReplenishStep(agent_id="MATERIAL_HANDLER", material="raw_material"),
]

_PACKAGE_STEPS = [
    PackageStep(agent_id="PACKAGER", job_id="worker_a_batch"),
    PackageStep(agent_id="PACKAGER", job_id="worker_b_batch"),
    PackageStep(agent_id="PACKAGER", job_id="worker_c_batch"),
    PackageStep(agent_id="PACKAGER", job_id="worker_d_batch"),
]

# Reworks are conditional (only when inspection fails) — not required for completion.
_REWORK_STEPS: list[ReworkStep] = []


class ProductionLineFlexibleRoutingSim(ManufacturingSim):
    """11H: Four workers with flexible routing across four workstations,
    shared tools and raw materials, quality inspector, material handler,
    and packager."""

    def __init__(self) -> None:
        super().__init__(
            job_steps=_JOB_STEPS,
            inspect_steps=_INSPECT_STEPS,
            replenish_steps=_REPLENISH_STEPS,
            package_steps=_PACKAGE_STEPS,
            rework_steps=_REWORK_STEPS,
            resources=["STATION_1", "STATION_2", "STATION_3", "STATION_4", "TOOL_SUPPLY", "RAW_MATERIAL"],
        )
        self.load_from_metadata(_METADATA)
