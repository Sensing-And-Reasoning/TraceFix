"""Parallel build simulation config for task 10E."""

import json
from pathlib import Path

from benchmark.tools.sim_build import (
    BuildSim,
    CompileStep,
    LinkStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "10E" / "metadata.json").read_text()
)

_RESOURCES = ["CORE_LIB", "SHARED_TYPES"]

_COMPILE_STEPS = [
    CompileStep(agent_id="BUILDER_A", module="module_a"),
    CompileStep(agent_id="BUILDER_B", module="module_b"),
]

_LINK_STEPS = [
    LinkStep(agent_id="INTEGRATOR", modules=["module_a", "module_b"]),
]


class TwoBuildersSharedLibSim(BuildSim):
    """10E: Two builders compiling modules with a shared core library,
    plus an integrator linking the final artifact."""

    # 10E only has compile_module and link_modules (can_fail=False) — no
    # run_build_tests or validate_artifact tools, so override to empty.
    _DECISION_TOOLS: dict = {}

    def __init__(self) -> None:
        super().__init__(
            compile_steps=_COMPILE_STEPS,
            link_steps=_LINK_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
