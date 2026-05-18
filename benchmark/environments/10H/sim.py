"""Parallel build simulation config for task 10H."""

import json
from pathlib import Path

from benchmark.tools.sim_build import (
    BuildSim,
    BuildTestStep,
    CompileStep,
    LinkStep,
    ValidateStep,
)

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "10H" / "metadata.json").read_text()
)

_RESOURCES = ["API_TYPES", "BUILD_SLOTS", "CONFIG", "CORE_LIB", "DATA_MODELS"]

_COMPILE_STEPS = [
    CompileStep(agent_id="BUILDER_A", module="module_a"),
    CompileStep(agent_id="BUILDER_B", module="module_b"),
    CompileStep(agent_id="BUILDER_C", module="module_c"),
    CompileStep(agent_id="BUILDER_D", module="module_d"),
]

_BUILD_TEST_STEPS = [
    BuildTestStep(agent_id="TEST_RUNNER", module="module_a"),
    BuildTestStep(agent_id="TEST_RUNNER", module="module_b"),
    BuildTestStep(agent_id="TEST_RUNNER", module="module_c"),
    BuildTestStep(agent_id="TEST_RUNNER", module="module_d"),
]

_VALIDATE_STEPS = [
    ValidateStep(agent_id="VALIDATOR", artifact="module_a_artifact"),
    ValidateStep(agent_id="VALIDATOR", artifact="module_b_artifact"),
    ValidateStep(agent_id="VALIDATOR", artifact="module_c_artifact"),
    ValidateStep(agent_id="VALIDATOR", artifact="module_d_artifact"),
]

_LINK_STEPS = [
    LinkStep(agent_id="INTEGRATOR", modules=["module_a", "module_b", "module_c", "module_d"]),
]


class FourBuildersBuildSlotsSim(BuildSim):
    """10H: Four builders with build slots and cascading rebuilds,
    an artifact validator, test runner, and integrator.

    BUILD_SLOTS is a counting semaphore (capacity=2) — at most 2 builds
    run concurrently.  Each builder acquires a slot before compiling and
    releases it afterward.  compile_module uses per-agent resources
    (BUILD_SLOTS + the builder's artifact locks) via metadata @agent_resources.
    """

    def __init__(self) -> None:
        super().__init__(
            compile_steps=_COMPILE_STEPS,
            build_test_steps=_BUILD_TEST_STEPS,
            validate_steps=_VALIDATE_STEPS,
            link_steps=_LINK_STEPS,
            resources=_RESOURCES,
            resource_capacities={"BUILD_SLOTS": 2},
        )
        self.load_from_metadata(_METADATA)
