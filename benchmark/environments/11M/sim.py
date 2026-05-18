"""Flexible manufacturing simulation config for task 11M."""

import json
from pathlib import Path

from benchmark.tools.sim_manufacturing import (
    InspectStep,
    JobStep,
    ManufacturingSim,
    ReworkStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "11M" / "metadata.json").read_text()
)

_JOB_STEPS = [
    JobStep(agent_id="WORKER_A", job_id="alpha_job_a"),
    JobStep(agent_id="WORKER_A", job_id="beta_job_a"),
    JobStep(agent_id="WORKER_B", job_id="beta_job_b"),
    JobStep(agent_id="WORKER_B", job_id="gamma_job_b"),
    JobStep(agent_id="WORKER_C", job_id="gamma_job_c"),
    JobStep(agent_id="WORKER_C", job_id="alpha_job_c"),
]

_INSPECT_STEPS = [
    InspectStep(agent_id="INSPECTOR", job_id="alpha_job_a"),
    InspectStep(agent_id="INSPECTOR", job_id="beta_job_a"),
    InspectStep(agent_id="INSPECTOR", job_id="beta_job_b"),
    InspectStep(agent_id="INSPECTOR", job_id="gamma_job_b"),
    InspectStep(agent_id="INSPECTOR", job_id="gamma_job_c"),
    InspectStep(agent_id="INSPECTOR", job_id="alpha_job_c"),
]

# Reworks are conditional (only when inspection fails) — not required for completion.
_REWORK_STEPS: list[ReworkStep] = []


class ThreeWorkerToolCabinetSim(ManufacturingSim):
    """11M: Three workers with shared tool cabinet, three workstations,
    a quality inspector, and a dispatcher for rework orders."""

    def __init__(self) -> None:
        super().__init__(
            job_steps=_JOB_STEPS,
            inspect_steps=_INSPECT_STEPS,
            rework_steps=_REWORK_STEPS,
            resources=["STATION_ALPHA", "STATION_BETA", "STATION_GAMMA", "TOOL_CABINET"],
        )
        self.load_from_metadata(_METADATA)
