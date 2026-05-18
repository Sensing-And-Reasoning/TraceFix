"""Parameterized parallel build simulation (scenarios 10E/10M/10H)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._base import ToolResult
from .sim_base import SimContext


@dataclass
class CompileStep:
    """A module compilation step."""

    agent_id: str
    module: str


@dataclass
class BuildTestStep:
    """A build test step."""

    agent_id: str
    module: str


@dataclass
class ValidateStep:
    """An artifact validation step."""

    agent_id: str
    artifact: str


@dataclass
class LinkStep:
    """A module linking step."""

    agent_id: str
    modules: list[str]


class BuildSim(SimContext):
    """Simulation for parallel build pipelines.

    Tracks per-agent progress through compilation, testing, validation,
    and linking phases.  Detects concurrent resource violations based on
    resources declared in _TOOL_RESOURCES (overridable per subclass).

    Args:
        compile_steps: Module compilation steps.
        build_test_steps: Build test steps.
        validate_steps: Artifact validation steps.
        link_steps: Module linking steps.
        resources: List of shared resource names to initialize (with optional capacities).
        resource_capacities: Per-resource capacity overrides (default capacity=1).
    """

    def __init__(
        self,
        compile_steps: list[CompileStep] | None = None,
        build_test_steps: list[BuildTestStep] | None = None,
        validate_steps: list[ValidateStep] | None = None,
        link_steps: list[LinkStep] | None = None,
        resources: list[str] | None = None,
        resource_capacities: dict[str, int] | None = None,
    ) -> None:
        super().__init__()

        self._compile_steps = {f"{s.agent_id}_{s.module}": s for s in (compile_steps or [])}
        self._build_test_steps = {f"{s.agent_id}_{s.module}": s for s in (build_test_steps or [])}
        self._validate_steps = {f"{s.agent_id}_{s.artifact}": s for s in (validate_steps or [])}
        self._link_steps = {f"{s.agent_id}_{'_'.join(s.modules)}": s for s in (link_steps or [])}

        self._compile_done: dict[str, bool] = {k: False for k in self._compile_steps}
        self._build_test_done: dict[str, bool] = {k: False for k in self._build_test_steps}
        self._validate_done: dict[str, bool] = {k: False for k in self._validate_steps}
        self._link_done: dict[str, bool] = {k: False for k in self._link_steps}

        self._agent_compile_count: dict[str, int] = {}

        caps = resource_capacities or {}
        for res in (resources or []):
            self.init_resource(res, capacity=caps.get(res, 1))

    # -- Decision tools (probabilistic failure for either/or branches) --

    _DECISION_TOOLS: dict[str, float] = {
        "run_build_tests": 0.3,
        "validate_artifact": 0.2,
    }

    # -- Resource requirements --

    _TOOL_RESOURCES: dict[str, list[str]] = {
        "compile_module": ["BUILD_SERVER"],
        "run_build_tests": ["BUILD_SERVER"],
        "validate_artifact": ["ARTIFACT_STORE"],
        "link_modules": ["BUILD_SERVER", "ARTIFACT_STORE"],
    }

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        # Prefer metadata-driven map (loaded via load_from_metadata) when available.
        if self._tool_resource_map:
            return super().resource_requirements(tool_name, **kwargs)
        return list(self._TOOL_RESOURCES.get(tool_name, []))

    # -- Simulated delays --

    _TOOL_DELAYS: dict[str, tuple[float, float]] = {
        "compile_module": (2.0, 5.0),
        "run_build_tests": (1.5, 4.0),
        "validate_artifact": (0.5, 1.5),
        "link_modules": (1.0, 3.0),
    }

    def tool_delay(self, tool_name: str, **kwargs: Any) -> tuple[float, float]:
        return self._TOOL_DELAYS.get(tool_name, (0.0, 0.0))

    # -- Tool implementations --

    @staticmethod
    def _normalize_module(value: str) -> str:
        """Normalize module name to match sim step keys (e.g. 'Module A' → 'module_a')."""
        return value.strip().lower().replace(" ", "_")

    def compile_module(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Compile a module. Resource requirements depend on subclass _TOOL_RESOURCES."""
        module = self._normalize_module(
            kwargs.get("module_name", kwargs.get("module", "unknown"))
        )

        self._mark_done(self._compile_done, agent_id, module)

        count = self._agent_compile_count.get(agent_id, 0)
        modified = count == 0  # first compile modifies artifacts; rebuilds don't
        self._agent_compile_count[agent_id] = count + 1

        result = {"module": module, "status": "compiled",
                  "artifacts_modified": modified, "agent": agent_id}
        message = f"Compiled: {module}" + (" (artifacts modified)" if modified else " (no artifact changes)")
        self.log_event(agent_id, "compile_module", {"module": module},
                       success=True, result=result)
        return ToolResult(tool_name="compile_module", success=True,
                          data=result, message=message)

    def run_build_tests(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Run build tests. Resource requirements depend on subclass _TOOL_RESOURCES."""
        module = self._normalize_module(
            kwargs.get("module_name", kwargs.get("module", "unknown"))
        )

        if self.should_fail("run_build_tests", agent_id):
            result = {"module": module, "status": "tests failed",
                      "test_result": "fail", "agent": agent_id}
            self.log_event(agent_id, "run_build_tests", {"module": module},
                           success=False, result=result)
            return ToolResult(tool_name="run_build_tests", success=False,
                              data=result, message=f"Build tests FAILED: {module}")

        self._mark_done(self._build_test_done, agent_id, module)

        result = {"module": module, "status": "tests passed",
                  "test_result": "pass", "agent": agent_id}
        self.log_event(agent_id, "run_build_tests", {"module": module},
                       success=True, result=result)
        return ToolResult(tool_name="run_build_tests", success=True,
                          data=result, message=f"Build tests PASSED: {module}")

    def validate_artifact(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Validate an artifact. Resource requirements depend on subclass _TOOL_RESOURCES."""
        artifact = kwargs.get("artifact", "unknown")

        if self.should_fail("validate_artifact", agent_id):
            result = {"artifact": artifact, "status": "validation failed",
                      "validation_result": "fail", "agent": agent_id}
            self.log_event(agent_id, "validate_artifact", {"artifact": artifact},
                           success=False, result=result)
            return ToolResult(tool_name="validate_artifact", success=False,
                              data=result, message=f"Validation FAILED: {artifact}")

        self._mark_done(self._validate_done, agent_id, artifact)

        result = {"artifact": artifact, "status": "validated",
                  "validation_result": "pass", "agent": agent_id}
        self.log_event(agent_id, "validate_artifact", {"artifact": artifact},
                       success=True, result=result)
        return ToolResult(tool_name="validate_artifact", success=True,
                          data=result, message=f"Validation PASSED: {artifact}")

    def link_modules(self, agent_id: str, **kwargs: Any) -> ToolResult:
        """Link modules into final artifact. Resource requirements depend on subclass _TOOL_RESOURCES."""
        raw = kwargs.get("modules", [])
        # Normalize: accept comma-separated string or list, normalize each name
        if isinstance(raw, str):
            modules = [self._normalize_module(m) for m in raw.split(",")]
        else:
            modules = [self._normalize_module(m) for m in raw]

        self._mark_done(self._link_done, agent_id, '_'.join(modules) if modules else 'all')

        result = {"modules": ", ".join(modules), "status": "linked", "agent": agent_id}
        self.log_event(agent_id, "link_modules", {"modules": modules},
                       success=True, result=result)
        return ToolResult(tool_name="link_modules", success=True,
                          data=result, message=f"Linked: {', '.join(modules) if modules else 'all'}")

    # -- SimContext interface --

    def make_tools(self) -> dict[str, Any]:
        return {
            "compile_module": self.compile_module,
            "run_build_tests": self.run_build_tests,
            "validate_artifact": self.validate_artifact,
            "link_modules": self.link_modules,
        }

    def is_complete(self) -> bool:
        return (all(self._compile_done.values()) and
                all(self._build_test_done.values()) and
                all(self._validate_done.values()) and
                all(self._link_done.values()))

    @property
    def progress(self) -> dict[str, Any]:
        return {
            "compilations": dict(self._compile_done),
            "build_tests": dict(self._build_test_done),
            "validations": dict(self._validate_done),
            "links": dict(self._link_done),
            "all_complete": self.is_complete(),
        }
