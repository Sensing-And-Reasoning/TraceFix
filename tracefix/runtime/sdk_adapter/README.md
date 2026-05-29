# SDK Adapter: Claude Agent SDK harness for tracefix protocols

Drives tracefix-verified coordination protocols using the **Claude Agent SDK**
(`claude-agent-sdk`) as the per-agent LLM harness, instead of the built-in
`monitoring/agent_runner.py` loop.

This realizes the "tracefix = verification layer, harness = pluggable" split:
tracefix produces the verified artifacts (IR, `states.json`, per-agent prompts)
and owns the coordination primitives + Monitor; the harness provides the LLM
loop and real work tools (Read / Write / Edit / Bash).

## Why this exists

The built-in monitoring agents only have dummy/sim domain tools, so they
execute the *coordination* protocol but can't produce real artifacts. By
swapping in the Claude Agent SDK, each sub-agent gets a production-grade LLM
loop **and** real file/shell tools — while the verified coordination layer
(`CoordinationContext` + `ProtocolMonitor` + `StateTracker`) is reused
**completely unchanged**.

## Design

```
        ir.json + states.json + prompts/runtime_b/<AGENT>.md   (from the pipeline)
                                  │
                    ┌─────────────┴──────────────┐
                    │     SdkOrchestrator         │
                    │  builds ONE shared          │
                    │  CoordinationContext +      │   ← reused unchanged from monitoring/
                    │  ProtocolMonitor + Tracker  │
                    └─────────────┬──────────────┘
              per agent ──────────┼───────────────── per agent
        ┌───────────────────┐         ┌───────────────────┐
        │ CoordToolDispatcher│  ...    │ CoordToolDispatcher│   (agent_id bound here)
        │  + in-process MCP  │         │  + in-process MCP  │
        └─────────┬─────────┘         └─────────┬─────────┘
        Claude Agent SDK query()      Claude Agent SDK query()   (concurrent, asyncio.gather)
        + Read/Write/Edit/Bash        + Read/Write/Edit/Bash
```

**`agent_id` binding.** Each agent gets its *own* in-process MCP server whose
tool handlers close over that agent's `CoordToolDispatcher` (which holds the
`agent_id`). The LLM therefore never passes its own id — it just calls
`acquire_lock(lock_id=...)` and the server already knows who is calling. This
keeps tool calls identical to what the tracefix-generated prompts reference.

**Tool names.** Coordination + domain tools are exposed under the MCP server
name `tracefix`, so they appear to the model as `mcp__tracefix__acquire_lock`,
`mcp__tracefix__send_message`, etc. They are built dynamically from the same
OpenAI-style schemas the monitoring runtime uses (`COORD_TOOL_SCHEMAS` + the
benchmark `ToolRegistry` domain schemas), so names and parameters match the
prompts exactly.

## Modules

| File | Purpose |
|------|---------|
| `types.py` | `ToolCall` / `AgentResult` dataclasses (field-compatible with monitoring; defined here so the adapter doesn't import the OpenAI SDK) |
| `dispatch.py` | `CoordToolDispatcher` — SDK-free mapping of a tool call onto `CoordinationContext` (the unit-tested core) |
| `mcp_server.py` | Builds a per-agent in-process SDK MCP server from the OpenAI schemas (lazy SDK import) |
| `sdk_runner.py` | Runs one agent via the SDK `query()` loop, returns an `AgentResult` |
| `orchestrator.py` | Loads a workspace, wires the shared coordination layer, runs N agents concurrently |
| `cli.py` / `__main__.py` | `python -m tracefix.runtime.sdk_adapter run ...` |

## Prerequisites

```bash
pip install claude-agent-sdk        # the Python SDK
```

A live run additionally needs (the offline tests below do NOT):
- the **Claude CLI** on PATH (`claude`) and Node.js — the SDK drives the CLI under the hood
- credentials — either be logged into the Claude CLI, or set `ANTHROPIC_API_KEY`

## Usage

```bash
# 1. Produce a verified workspace with the pipeline (one-time, per task):
python -m tracefix.pipeline --benchmark 3E --verbose
#    → workspace with ir.json, states.json, prompts/runtime_b/<AGENT>.md

# 2. Run that workspace with SDK-driven agents:
python -m tracefix.runtime.sdk_adapter run --task 3E --workspace path/to/workspace --verbose

# Give agents real work tools + a model override:
python -m tracefix.runtime.sdk_adapter run --task 3E --workspace ws/3E \
    --model claude-sonnet-4-6 --builtins Read,Write,Edit,Bash --max-rounds 40
```

`--builtins` is a comma-separated allow-list of SDK built-in tools (default
`Read,Write,Edit`; pass empty to disable). Sim flags (`--scenario`,
`--difficulty`, `--tool-time`, `--seed`) mirror the monitoring CLI for
scenarios 12–16.

## Tests

```bash
pytest tracefix/runtime/sdk_adapter/tests/ -v
```

- `test_dispatch.py` (7) — **SDK-free.** Exercises `CoordToolDispatcher` against
  a real `CoordinationContext` + `ProtocolMonitor`: acquire/send/receive/release,
  Counter semaphore, Monitor rejecting an illegal send, `signal_done` gating,
  unknown-tool / missing-arg handling, schema conversion.
- `test_sdk_integration.py` (3) — **skipped unless `claude-agent-sdk` is
  installed.** Validates the adapter↔SDK boundary offline: required symbols
  exist, `ClaudeAgentOptions` accepts the runner's kwargs, and the coordination
  schemas build into a real in-process MCP server.

## Validation status

Validated (offline, this machine):
- ✅ Dispatcher drives the real `CoordinationContext`; Monitor violations surface as tool errors
- ✅ `claude-agent-sdk` 0.2.x exposes every symbol/option the adapter uses
- ✅ Coordination schemas build into a real in-process MCP server

Not yet exercised:
- ⏳ A live multi-agent `query()` run (needs an authenticated Claude CLI + a
  pipeline-generated workspace). The public repo ships no workspace.

## Limitations / follow-ups

- **Architecture B only.** Architecture A (enforcement) has the engine drive
  agents, which is incompatible with the SDK's self-driven model.
- **Built-in tools are allow-listed, not hard-sandboxed.** `permission_mode`
  is `bypassPermissions` (headless). Tighten with `disallowed_tools` if needed.
- **Live visualization not wired.** The dispatcher already emits
  `agent.tool_call` events if given an `EventBus`; hooking the SSE server is a
  follow-up.
- **Large artifacts** should be passed via the shared workspace (Write a file,
  then `send_message` a label/pointer) rather than stuffed into a message body.
