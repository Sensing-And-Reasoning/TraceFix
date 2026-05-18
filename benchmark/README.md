# Benchmark

Unified benchmark package for multi-agent coordination tasks. Contains 16 scenarios (48 tasks across Easy/Medium/Hard difficulties), with task descriptions, per-agent tool schemas, simulation environments, and coordination checklists.

## Structure

```
benchmark/
├── loader.py              # Task discovery & metadata loading
├── descriptions/{id}/     # Agent-visible task specs (48 folders)
│   ├── description.md     # Task narrative (agents, resources, workflow, goal)
│   ├── tools.json         # Per-agent tool schemas (OpenAI function-calling format)
│   └── metadata.json      # Agent names + resource names
├── environments/{id}/     # Simulation environments (48 folders)
│   ├── sim.py             # Sim class instantiation (imports from tools/sim_*.py)
│   ├── tools_impl.py      # Dummy tool implementations (fallback when sim not used)
│   └── checklist.json     # Coordination requirement checklist
├── tools/                 # Tool framework
│   ├── _base.py           # ToolConfig, ToolResult, @dummy_tool decorator
│   ├── _registry.py       # ToolRegistry: schema loading, dispatch, per-agent filtering
│   ├── sim_base.py        # SimContext ABC: resource management, failure injection, violation logging
│   └── sim_*.py           # Domain-specific simulators (kitchen, pharma, cicd, etc.)
└── tests/                 # Test suite
```

## Scenarios

| # | Name | Difficulty | Domain |
|---|------|-----------|--------|
| 1 | Shared Codebase Development | E/M/H | Concurrent module locking |
| 2 | Research Paper Writing | E/M/H | Section locking, cross-references |
| 3 | Two-Author Research Report | E/M/H | Document/database locking, review loop |
| 4 | Software Development Pipeline | E/M/H | Repo locking, code review, testing |
| 5 | Emergency Medical Response | E/M/H | Equipment sharing, patient handoff |
| 6 | Shared Utility File Conflict | E/M/H | Repo locking, code review |
| 7 | Document Authoring | E/M/H | Document/figure locking, fact-checking |
| 8 | API System Development | E/M/H | Database/API locking, testing |
| 9 | Dining Philosophers | E/M/H | Fork locking, deadlock avoidance |
| 10 | Build System | E/M/H | Shared library/types locking, rebuild cascades |
| 11 | Manufacturing Line | E/M/H | Station/tool locking, inspection, rework |
| 12 | Collaborative Kitchen | E/M/H | Equipment sharing, ingredient exchange, cooking failures |
| 13 | Pharmaceutical Lab | E/M/H | Instrument sharing, reagent pool, quality control |
| 14 | Drug Discovery Pipeline | E/M/H | Instrument sharing, sample pool, multi-round trials |
| 15 | Semiconductor Fabrication | E/M/H | Chamber/stepper locking, wafer slots, rework |
| 16 | CI/CD Pipeline | E/M/H | Build server, artifact store, staging/prod environments |

Scenarios 1–11 are coordination-only tasks. Scenarios 12–16 have full simulation environments with failure injection.

## Task Loading

```python
from benchmark.loader import load_task, list_task_ids, TaskEntry

# List all 48 task IDs
ids = list_task_ids()  # ['1E', '1M', '1H', '2E', ..., '16H']

# Load a single task
task = load_task("3E")
task.task_id       # "3E"
task.task_name     # "Two-Author Research Report"
task.scenario      # "Two-Author Research Report"
task.difficulty    # "Easy"
task.description   # Full markdown text
task.checklist     # List of coordination requirements (from checklist.json)
```

## Tool Framework

### ToolRegistry

Loads tool schemas from `descriptions/{id}/tools.json`, dispatches calls to either sim-mode or dummy-mode:

```python
from benchmark.tools import load_tools, ToolConfig

# Dummy-mode (no simulation, mock responses)
registry = load_tools("3E")

# Sim-mode (full simulation with state tracking)
from benchmark.environments.12E.sim import KitchenBasicSim
sim = KitchenBasicSim()
registry = load_tools("12E", sim=sim)

# Per-agent tool filtering
tools = registry.tools_for_agent("CHEF_A")    # Only tools with CHEF_A in agent_ids
schemas = registry.openai_schemas("CHEF_A")   # OpenAI function-calling format

# Call a tool
result = await registry.call("prepare_base_dish", agent_id="CHEF_A", dish="appetizer")
result.success    # True/False
result.data       # {"dish": "appetizer", "status": "base dish prepared"}
```

### SimContext

Base class for domain-specific simulators. Provides:

- **Resource management**: `init_resource()`, `try_acquire()`, `release()`, `holder_of()`
- **Failure injection**: `set_difficulty(0-3)`, `set_scenario_depth(N)`, `should_fail()`
- **Violation logging**: `log_violation()`, `log_event()`, `.violations`, `.events`
- **Progress tracking**: `is_complete()`, `progress` property
- **Per-agent RNG**: Seeded from `--seed` XOR agent ID hash for reproducibility

### Failure Injection

Two mutually exclusive modes for decision-point tools (tools whose outcome determines protocol branching):

| Mode | Flag | Behavior |
|------|------|----------|
| Probabilistic | `--difficulty 0-3` | 0%/30%/60%/90% failure rate per decision-point tool call |
| Deterministic | `--scenario N` | First N calls per tool per agent fail, then succeed |

Orthogonal parameters: `--tool-time` (delay multiplier), `--seed` (reproducible RNG).

## Tool Schema Format

Each `tools.json` contains an array of OpenAI function-calling tool definitions with two extra fields:

```json
{
  "type": "function",
  "function": {
    "name": "cook_on_stovetop",
    "description": "Cook a dish on the stovetop. Can fail.",
    "agent_ids": ["CHEF_A", "CHEF_B"],
    "can_fail": true,
    "parameters": {
      "type": "object",
      "properties": { "item": { "type": "string" } },
      "required": ["item"]
    }
  }
}
```

- `agent_ids`: Which agents can use this tool (empty = all agents). Stripped before sending to LLM.
- `can_fail`: Whether this tool is a decision-point tool subject to failure injection. Stripped before sending to LLM.

## Checklist Format

Each `checklist.json` describes coordination requirements for semantic fidelity checking:

```json
[
  {"id": "res_oven", "type": "resource", "description": "OVEN modeled as Lock"},
  {"id": "ch_sauce", "type": "dependency", "description": "channel from CHEF_A to CHEF_C"},
  {"id": "ord_dessert", "type": "ordering", "description": "dessert requires receiving sauce first"},
  {"id": "acc_base_oven", "type": "resource_access", "description": "base dish prep acquires OVEN"},
  {"id": "parallel_start", "type": "concurrency", "description": "all chefs start concurrently"}
]
```

Types: `resource`, `dependency`, `ordering`, `resource_access`, `concurrency`.

## Tests

```bash
pytest benchmark/tests/ -v
```

- `test_loader.py` — Task discovery (48 tasks), scenario/difficulty mapping, checklist loading
- `test_sim_kitchen.py` — Kitchen simulation: happy path, prerequisite violations, resource contention, progress tracking
- `test_sim_cicd.py` — CI/CD simulation: build/test/deploy pipeline, violation detection
