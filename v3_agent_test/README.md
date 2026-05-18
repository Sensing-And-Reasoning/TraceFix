# v3_agent: Optimized Agentic TLA+ Verification Agent

Fork of `v3_agent` with TLC state space optimizations and IR design improvements. Created to address Hard benchmark tasks (3H, 4H) that timed out due to state space explosion in the original `v3_agent`.

See [CHANGELOG.md](CHANGELOG.md) for detailed changes from `v3_agent`.

## Key Optimizations over v3_agent

1. **Channel Depth CONSTRAINT** — bounds per-channel states from unbounded to `channel_bound` (default 3)
2. **Agent-Specific Next Formula** — eliminates unnecessary guard evaluations (107 vs 749 per state for 7 agents)
3. **String Messages** — `"prepare"` instead of `[label |-> "prepare"]`, simpler state representation
4. **Multi-Core TLC** — `-workers auto` + `-Xmx4g` JVM heap
5. **Safety-Only Verification** — no liveness checking, deadlock detected natively by TLC
6. **One Channel Per Directed Pair** — `labels` field distinguishes message types, reduces channel proliferation
7. **Counter Semantics** — Counter = shared resource pool only, NOT for loop bounds

## Usage

```bash
# Custom task
python -m v3_agent --task "Design a 2PC protocol with coordinator and 2 banks"

# Benchmark tasks
python -m v3_agent --benchmark 1E
python -m v3_agent --benchmark 2M --level L2
python -m v3_agent --benchmark 3E 4H --level L3

# Run all benchmarks
python -m v3_agent --benchmark-all
python -m v3_agent --benchmark-all --difficulty E --parallel 3
python -m v3_agent --benchmark-all --difficulty H --scenario 3 4 --level L3

# Level sweep: run each task at all 3 levels (L1, L2, L3)
python -m v3_agent --benchmark 1E --level-sweep
python -m v3_agent --benchmark-all --difficulty E --level-sweep --parallel 4

# Options
python -m v3_agent --benchmark 1E --model gpt-5 --provider openai
python -m v3_agent --benchmark 1E --provider openrouter --model minimax/minimax-m2.5
python -m v3_agent --benchmark 1E --max-turns 15 --verbose
```

## Architecture

```
cli.py ──> AgentLoop (loop.py)
              |
              |-> ToolClient (tool_client.py)  -- OpenAI / Anthropic / OpenRouter API
              |       translates canonical messages to provider format
              |
              |-> Workspace (workspace.py)     -- file-based session directory
              |       ir.json, Protocol.tla, Protocol.cfg, tlc_output.log, ...
              |
              +-> Tool Registry (tools.py)     -- 10 tools wrapping pipeline modules
                      think, write_file, read_file, edit_file, list_files
                      validate_ir, compile_tla, run_tlc, verify_ir
                      load_benchmark
```

## Modules

| File | Purpose |
|------|---------|
| `cli.py` | CLI parser, task runner, parallel benchmark executor |
| `loop.py` | Think-act-observe agent loop with context compression + doom-loop detection |
| `tools.py` | 10 tool schemas + implementations wrapping pipeline modules |
| `tool_client.py` | Provider-agnostic LLM client with tool calling (OpenAI + Anthropic + OpenRouter) |
| `workspace.py` | File workspace with structured result tracking |
| `prompts.py` | System prompt: IR schema, rules, anti-patterns, 2PC example |
| `session.py` | Session recording to JSON |
| `pipeline/validator.py` | IR schema + semantic validation (incl. channel label checks) |
| `pipeline/skeleton_generator.py` | Deterministic IR -> TLA+ + TLC config (optimized) |
| `pipeline/tlc_runner.py` | TLC execution wrapper (multi-core, safety-only) |
| `pipeline/trace_parser.py` | TLC counterexample trace parsing |
| `pipeline/llm_client.py` | Multi-provider LLM client for sub-agent calls (summarizer) |
| `pipeline/error_formatter.py` | TLC error formatting for LLM repair prompts |
| `pipeline/schema.json` | IR v3 JSON Schema (with required `labels` on channels) |

## Available Tools

| Tool | Type | Description |
|------|------|-------------|
| `think` | Reasoning | Plan approach, no side effects |
| `write_file` | File | Write any file; auto-clears downstream on ir.json change |
| `read_file` | File | Read any workspace file |
| `edit_file` | File | Surgical string replacement |
| `list_files` | File | List all workspace files |
| `validate_ir` | Verification | Schema + semantic validation of ir.json |
| `compile_tla` | Verification | Deterministic IR -> TLA+ (skeleton generator) |
| `run_tlc` | Verification | Run TLC model checker (safety-only) |
| `verify_ir` | Verification | **Preferred.** One-step: validate + compile + TLC |
| `load_benchmark` | Workflow | Load benchmark_new task by ID + level |

## Workspace Structure

Each run creates a workspace in `v3_agent/results/{experiment_ts}/workspaces/{session_id}/`:

```
workspace/
+-- task.md           # Task description
+-- ir.json           # Current IR v3 specification
+-- Protocol.tla      # Generated TLA+ spec
+-- Protocol.cfg      # TLC configuration
+-- tlc_output.log    # Raw TLC output
+-- tlc_error.md      # Formatted error (on failure)
+-- notes/            # Agent's analysis and reasoning
+-- session.json      # Full execution trace
```

## CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--task` | -- | Natural language task description |
| `--benchmark` | -- | Benchmark task ID(s) (e.g., `1E 2M 5H`) |
| `--benchmark-all` | -- | Run all benchmark tasks |
| `--provider` | `openai` | LLM provider (`openai`, `anthropic`, `openrouter`) |
| `--model` | `gpt-5` | Model name |
| `--level` | `L1` | Description detail level (`L1`/`L2`/`L3`) |
| `--level-sweep` | off | Run each task at all 3 levels |
| `--difficulty` | all | Filter: `E`, `M`, `H` (benchmark-all only) |
| `--scenario` | all | Filter by scenario number (benchmark-all only) |
| `--trials` | `1` | Number of trials per task |
| `--parallel` | `1` | Concurrent tasks |
| `--max-turns` | `40` | Max agent loop iterations |
| `--reasoning-effort` | `high` (openai) | Reasoning effort for reasoning models |
| `--thinking-budget` | `0` | Anthropic extended thinking token budget |
| `--max-tokens` | `32768` | Max output tokens |
| `--verbose` | off | Print tool calls to stderr |
| `--no-save` | off | Don't save session JSON |
| `--no-summarize` | off | Disable LLM-based context compression |
