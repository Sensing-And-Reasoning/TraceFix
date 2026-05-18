"""Parallel build simulation config for task 10M."""

import json
from pathlib import Path

from benchmark.tools.sim_build import (
    BuildSim,
    BuildTestStep,
    CompileStep,
    LinkStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "10M" / "metadata.json").read_text()
)

_RESOURCES = ["CONFIG", "CORE_LIB", "DATA_MODELS"]

_COMPILE_STEPS = [
    CompileStep(agent_id="BUILDER_A", module="module_a"),
    CompileStep(agent_id="BUILDER_B", module="module_b"),
    CompileStep(agent_id="BUILDER_C", module="module_c"),
]

_BUILD_TEST_STEPS = [
    BuildTestStep(agent_id="TEST_RUNNER", module="module_a"),
    BuildTestStep(agent_id="TEST_RUNNER", module="module_b"),
    BuildTestStep(agent_id="TEST_RUNNER", module="module_c"),
]

_LINK_STEPS = [
    LinkStep(agent_id="INTEGRATOR", modules=["module_a", "module_b", "module_c"]),
]


class ThreeBuildersOverlappingDepsSim(BuildSim):
    """10M: Three builders with overlapping shared artifact dependencies,
    a test runner, and an integrator.

    run_build_tests has a retry loop (fail → rebuild), so it is a decision
    tool.  validate_artifact is not used in 10M, so override to exclude it.
    """

    # 10M uses run_build_tests (with retry on fail) but not validate_artifact.
    _DECISION_TOOLS: dict = {"run_build_tests": 0.3}

    def __init__(self) -> None:
        super().__init__(
            compile_steps=_COMPILE_STEPS,
            build_test_steps=_BUILD_TEST_STEPS,
            link_steps=_LINK_STEPS,
            resources=_RESOURCES,
        )
        self.load_from_metadata(_METADATA)
