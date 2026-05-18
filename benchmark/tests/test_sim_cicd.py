"""Tests for CI/CD pipeline simulation environment (task 16M)."""

import importlib

import pytest

from benchmark.tools import ToolConfig, load_tools
from benchmark.tools.sim_cicd import CICDSim

_sim_16m = importlib.import_module("benchmark.environments.16M.sim")
CICDPipelineSim = _sim_16m.CICDPipelineSim


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_happy_path(sim: CICDSim):
    """Execute a correct full pipeline sequence (progress tracking only)."""
    # Frontend build
    sim.compile_code("FRONTEND_DEV", "frontend")
    sim.run_unit_tests("FRONTEND_DEV", "frontend")
    sim.publish_artifact("FRONTEND_DEV", "frontend_image")

    # Backend build
    sim.compile_code("BACKEND_DEV", "backend")
    sim.run_unit_tests("BACKEND_DEV", "backend")
    sim.publish_artifact("BACKEND_DEV", "backend_image")

    # QA: pull artifacts -> run tests
    sim.pull_artifacts("QA_ENGINEER", "test_harness")
    sim.run_integration_tests("QA_ENGINEER", "api_integration")
    sim.run_e2e_tests("QA_ENGINEER", "user_flows")

    # Release eng: staging deploy -> smoke -> prod deploy -> smoke
    sim.pull_artifacts("RELEASE_ENGINEER", "staging_deploy")
    sim.deploy_staging("RELEASE_ENGINEER", "full_stack")
    sim.run_smoke_tests("RELEASE_ENGINEER", "staging")

    sim.pull_artifacts("RELEASE_ENGINEER", "production_deploy")
    sim.deploy_production("RELEASE_ENGINEER", "full_stack")
    sim.run_smoke_tests("RELEASE_ENGINEER", "production")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_full_pipeline(self):
        sim = CICDPipelineSim()
        _run_happy_path(sim)
        assert sim.is_complete()
        assert not sim.has_violations

    def test_no_violations_in_events(self):
        sim = CICDPipelineSim()
        _run_happy_path(sim)
        for ev in sim.events:
            assert ev.violations == [], f"Unexpected violation in {ev.tool}"


# ---------------------------------------------------------------------------
# Decoupled sim: tools succeed without lock checks (lock enforcement is runtime layer)
# ---------------------------------------------------------------------------

class TestDecoupledToolAccess:
    def test_compile_succeeds_without_lock(self):
        """Sim tools no longer check lock state — that's the runtime layer's job."""
        sim = CICDPipelineSim()
        result = sim.compile_code("FRONTEND_DEV", "frontend")
        assert result.success
        assert not sim.has_violations

    def test_publish_succeeds_without_locks(self):
        sim = CICDPipelineSim()
        result = sim.publish_artifact("FRONTEND_DEV", "frontend_image")
        assert result.success
        assert not sim.has_violations

    def test_deploy_production_succeeds_without_lock(self):
        sim = CICDPipelineSim()
        result = sim.deploy_production("RELEASE_ENGINEER", "full_stack")
        assert result.success
        assert not sim.has_violations

    def test_smoke_tests_succeed_without_lock(self):
        sim = CICDPipelineSim()
        result = sim.run_smoke_tests("RELEASE_ENGINEER", "production")
        assert result.success
        assert not sim.has_violations


# ---------------------------------------------------------------------------
# Infrastructure contention
# ---------------------------------------------------------------------------

class TestInfrastructureContention:
    def test_two_devs_same_build_server(self):
        """Second developer gets blocked — not a violation."""
        sim = CICDPipelineSim()
        assert sim.try_acquire("BUILD_SERVER", "FRONTEND_DEV")
        assert not sim.try_acquire("BUILD_SERVER", "BACKEND_DEV")
        assert sim.holder_of("BUILD_SERVER") == "FRONTEND_DEV"
        assert not sim.has_violations

    def test_qa_and_release_test_env_contention(self):
        """QA and release eng compete for test_env."""
        sim = CICDPipelineSim()
        assert sim.try_acquire("TEST_ENV", "QA_ENGINEER")
        assert not sim.try_acquire("TEST_ENV", "RELEASE_ENGINEER")
        assert not sim.has_violations

    def test_dev_holds_build_server_blocks_other(self):
        """While frontend holds build_server + artifact_store, backend cannot build."""
        sim = CICDPipelineSim()
        sim.try_acquire("BUILD_SERVER", "FRONTEND_DEV")
        sim.try_acquire("ARTIFACT_STORE", "FRONTEND_DEV")
        assert not sim.try_acquire("BUILD_SERVER", "BACKEND_DEV")
        assert not sim.try_acquire("ARTIFACT_STORE", "BACKEND_DEV")

    def test_artifact_store_contention_publish_vs_pull(self):
        """Dev publishing blocks QA from pulling."""
        sim = CICDPipelineSim()
        sim.try_acquire("BUILD_SERVER", "FRONTEND_DEV")
        sim.try_acquire("ARTIFACT_STORE", "FRONTEND_DEV")
        assert not sim.try_acquire("ARTIFACT_STORE", "QA_ENGINEER")
        assert sim.holder_of("ARTIFACT_STORE") == "FRONTEND_DEV"


# ---------------------------------------------------------------------------
# Deadlock scenario demonstrations
# ---------------------------------------------------------------------------

class TestDeadlockScenarios:
    """These tests demonstrate the hidden deadlock patterns in the task."""

    def test_abba_lock_ordering_scenario(self):
        """Deadlock 1: ABBA lock ordering."""
        sim = CICDPipelineSim()
        assert sim.try_acquire("BUILD_SERVER", "FRONTEND_DEV")
        assert sim.try_acquire("ARTIFACT_STORE", "BACKEND_DEV")
        assert not sim.try_acquire("ARTIFACT_STORE", "FRONTEND_DEV")
        assert not sim.try_acquire("BUILD_SERVER", "BACKEND_DEV")
        assert not sim.has_violations

    def test_test_env_circular_wait(self):
        """Deadlock 2: QA and Release both need test_env."""
        sim = CICDPipelineSim()
        assert sim.try_acquire("TEST_ENV", "QA_ENGINEER")
        assert not sim.try_acquire("TEST_ENV", "RELEASE_ENGINEER")

    def test_revision_cascade_resource_conflict(self):
        """Deadlock 3: Revision cascade."""
        sim = CICDPipelineSim()
        sim.try_acquire("BUILD_SERVER", "BACKEND_DEV")
        sim.try_acquire("ARTIFACT_STORE", "BACKEND_DEV")
        assert not sim.try_acquire("BUILD_SERVER", "FRONTEND_DEV")
        assert sim.holder_of("BUILD_SERVER") == "BACKEND_DEV"

    def test_qa_revision_artifact_conflict(self):
        """Deadlock 4: QA revision loop artifact conflict."""
        sim = CICDPipelineSim()
        sim.try_acquire("BUILD_SERVER", "FRONTEND_DEV")
        sim.try_acquire("ARTIFACT_STORE", "FRONTEND_DEV")
        assert not sim.try_acquire("ARTIFACT_STORE", "QA_ENGINEER")
        assert not sim.try_acquire("ARTIFACT_STORE", "RELEASE_ENGINEER")


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

class TestProgressTracking:
    def test_initial_progress(self):
        sim = CICDPipelineSim()
        p = sim.progress
        assert p["all_complete"] is False
        assert all(not v for v in p["compilations"].values())
        assert all(not v for v in p["unit_tests"].values())

    def test_progress_after_compile(self):
        sim = CICDPipelineSim()
        sim.compile_code("FRONTEND_DEV", "frontend")
        p = sim.progress
        assert p["compilations"]["FRONTEND_DEV_frontend"] is True
        assert p["compilations"]["BACKEND_DEV_backend"] is False
        assert p["all_complete"] is False

    def test_progress_after_complete(self):
        sim = CICDPipelineSim()
        _run_happy_path(sim)
        p = sim.progress
        assert p["all_complete"] is True


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    def test_load_tools_with_sim(self):
        sim = CICDPipelineSim()
        reg = load_tools("16M", config=ToolConfig(min_delay=0, max_delay=0), sim=sim)
        assert "compile_code" in reg.tool_names
        assert "deploy_production" in reg.tool_names
        assert "acquire_instrument" not in reg.tool_names
        assert len(reg.tool_names) == 9

    def test_tools_per_agent(self):
        sim = CICDPipelineSim()
        reg = load_tools("16M", config=ToolConfig(min_delay=0, max_delay=0), sim=sim)
        fe_tools = reg.tools_for_agent("FRONTEND_DEV")
        assert "compile_code" in fe_tools
        assert "run_unit_tests" in fe_tools
        assert "publish_artifact" in fe_tools
        assert "deploy_production" not in fe_tools

        qa_tools = reg.tools_for_agent("QA_ENGINEER")
        assert "run_integration_tests" in qa_tools
        assert "run_e2e_tests" in qa_tools
        assert "compile_code" not in qa_tools

        re_tools = reg.tools_for_agent("RELEASE_ENGINEER")
        assert "deploy_staging" in re_tools
        assert "deploy_production" in re_tools
        assert "pull_artifacts" in re_tools
        assert "compile_code" not in re_tools

    def test_build_master_has_no_domain_tools(self):
        """Build master is pure coordination — no domain tools."""
        sim = CICDPipelineSim()
        reg = load_tools("16M", config=ToolConfig(min_delay=0, max_delay=0), sim=sim)
        bm_tools = reg.tools_for_agent("BUILD_MASTER")
        assert bm_tools == []


# ---------------------------------------------------------------------------
# Concurrent resource usage detection
# ---------------------------------------------------------------------------

class TestConcurrentResourceUsage:
    """Tests for the begin/end resource tracking that detects two agents
    using the same infrastructure simultaneously (independent of locks)."""

    def test_resource_requirements_mapping(self):
        sim = CICDPipelineSim()
        assert sim.resource_requirements("compile_code") == ["BUILD_SERVER"]
        assert sim.resource_requirements("run_unit_tests") == ["BUILD_SERVER"]
        assert set(sim.resource_requirements("publish_artifact")) == {
            "BUILD_SERVER", "ARTIFACT_STORE",
        }
        assert sim.resource_requirements("pull_artifacts") == ["ARTIFACT_STORE"]
        assert sim.resource_requirements("run_integration_tests") == ["TEST_ENV"]
        assert sim.resource_requirements("run_e2e_tests") == ["TEST_ENV"]
        assert sim.resource_requirements("deploy_staging") == ["TEST_ENV"]
        assert sim.resource_requirements("deploy_production") == ["PROD_ENV"]

    def test_resource_requirements_smoke_tests_dynamic(self):
        sim = CICDPipelineSim()
        assert sim.resource_requirements("run_smoke_tests", target="staging") == ["TEST_ENV"]
        assert sim.resource_requirements("run_smoke_tests", target="production") == ["PROD_ENV"]

    def test_no_conflict_when_different_resources(self):
        sim = CICDPipelineSim()
        sim.begin_resource_use("FRONTEND_DEV", "compile_code", ["BUILD_SERVER"])
        violations = sim.begin_resource_use("QA_ENGINEER", "pull_artifacts", ["ARTIFACT_STORE"])
        assert violations == []
        assert not sim.has_violations

    def test_conflict_same_resource_different_agents(self):
        sim = CICDPipelineSim()
        sim.begin_resource_use("FRONTEND_DEV", "compile_code", ["BUILD_SERVER"])
        violations = sim.begin_resource_use("BACKEND_DEV", "run_unit_tests", ["BUILD_SERVER"])
        assert len(violations) == 1
        assert violations[0].violation_type == "concurrent_resource_use"
        assert "FRONTEND_DEV" in violations[0].message
        assert "BACKEND_DEV" in violations[0].message
        assert "BUILD_SERVER" in violations[0].message
        assert sim.has_violations

    def test_no_conflict_same_agent_same_resource(self):
        """Same agent reusing a resource is not a conflict."""
        sim = CICDPipelineSim()
        sim.begin_resource_use("FRONTEND_DEV", "compile_code", ["BUILD_SERVER"])
        violations = sim.begin_resource_use("FRONTEND_DEV", "run_unit_tests", ["BUILD_SERVER"])
        assert violations == []
        assert not sim.has_violations

    def test_end_clears_in_use(self):
        sim = CICDPipelineSim()
        sim.begin_resource_use("FRONTEND_DEV", "compile_code", ["BUILD_SERVER"])
        sim.end_resource_use("FRONTEND_DEV", ["BUILD_SERVER"])
        violations = sim.begin_resource_use("BACKEND_DEV", "compile_code", ["BUILD_SERVER"])
        assert violations == []
        assert not sim.has_violations

    def test_end_only_clears_own_resource(self):
        """end_resource_use for agent A does not clear agent B's usage."""
        sim = CICDPipelineSim()
        sim.begin_resource_use("FRONTEND_DEV", "compile_code", ["BUILD_SERVER"])
        sim.end_resource_use("BACKEND_DEV", ["BUILD_SERVER"])
        violations = sim.begin_resource_use("BACKEND_DEV", "compile_code", ["BUILD_SERVER"])
        assert len(violations) == 1
        assert violations[0].violation_type == "concurrent_resource_use"

    def test_multi_resource_partial_conflict(self):
        """publish_artifact needs both build_server + artifact_store.
        Conflict on one of the two resources."""
        sim = CICDPipelineSim()
        sim.begin_resource_use("FRONTEND_DEV", "compile_code", ["BUILD_SERVER"])
        violations = sim.begin_resource_use(
            "BACKEND_DEV", "publish_artifact", ["BUILD_SERVER", "ARTIFACT_STORE"],
        )
        assert len(violations) == 1
        assert "BUILD_SERVER" in violations[0].message
