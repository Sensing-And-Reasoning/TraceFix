# Task 11M: Three Workers with Shared Tool Cabinet

A workshop has three workstations (**STATION_ALPHA**, **STATION_BETA**, **STATION_GAMMA**) and a shared tool cabinet containing 2 specialized tools. Three workers each have two jobs requiring different workstations. Some jobs also require a tool from the cabinet. When a workstation is occupied, a worker works on a job at a different workstation instead of waiting. A quality **INSPECTOR** checks completed jobs, and a **DISPATCHER** sends rework orders when inspections fail.

## Agents

- **WORKER_A**: must complete two jobs — one on **STATION_ALPHA** (requires a tool) and one on **STATION_BETA** (no tool needed). Can choose which job to do first based on station availability.
- **WORKER_B**: must complete two jobs — one on **STATION_BETA** (requires a tool) and one on **STATION_GAMMA** (no tool needed). Can choose which job to do first based on station availability.
- **WORKER_C**: must complete two jobs — one on **STATION_GAMMA** (requires a tool) and one on **STATION_ALPHA** (no tool needed). Can choose which job to do first based on station availability.
- **INSPECTOR**: receives inspection requests, checks quality, and sends pass/fail results.
- **DISPATCHER**: receives fail results and sends rework orders to the appropriate worker.

## Shared Resources

- **STATION_ALPHA** workstation (can only be used by one worker at a time)
- **STATION_BETA** workstation (can only be used by one worker at a time)
- **STATION_GAMMA** workstation (can only be used by one worker at a time)
- **TOOL_CABINET** counter (initial=2, shared consumable tools that must be returned)

## Workflow

### WORKER_A
- Chooses an available workstation. If both **STATION_ALPHA** and **STATION_BETA** are available, the choice is nondeterministic.
- For the **STATION_ALPHA** job: uses the station and a tool from **TOOL_CABINET**, completes the job, returns the tool.
- For the **STATION_BETA** job: uses the station (no tool needed), completes the job.
- After completing a job, sends it for inspection via the inspection request channel.
- If inspection fails, receives rework order from **DISPATCHER** and redoes the failed job.

### WORKER_B
- Chooses an available workstation. If both **STATION_BETA** and **STATION_GAMMA** are available, the choice is nondeterministic.
- For the **STATION_BETA** job: uses the station and a tool from **TOOL_CABINET**, completes the job, returns the tool.
- For the **STATION_GAMMA** job: uses the station (no tool needed), completes the job.
- After completing a job, sends it for inspection via the inspection request channel.
- If inspection fails, receives rework order from **DISPATCHER** and redoes the failed job.

### WORKER_C
- Chooses an available workstation. If both **STATION_GAMMA** and **STATION_ALPHA** are available, the choice is nondeterministic.
- For the **STATION_GAMMA** job: uses the station and a tool from **TOOL_CABINET**, completes the job, returns the tool.
- For the **STATION_ALPHA** job: uses the station (no tool needed), completes the job.
- After completing a job, sends it for inspection via the inspection request channel.
- If inspection fails, receives rework order from **DISPATCHER** and redoes the failed job.

### INSPECTOR
- Receives inspection requests, checks quality one job at a time, and sends the result via the inspection result channel.

### DISPATCHER
- Receives fail results and sends rework orders via the rework channel. The worker must redo the failed job (re-use the workstation and tool if needed).

## Constraints

- Each workstation can only be used by one worker at a time.
- The **TOOL_CABINET** has 2 tools (Counter, initial=2). A job requiring a tool decrements the counter; the tool is returned after the job (counter incremented). If no tools are available, the worker must wait until a tool is returned.
- Each worker has two independent jobs on different workstations. When choosing which job to do first, the worker picks an available workstation. If both are available, the choice is nondeterministic.
- After completing a job, the worker sends it for inspection via the inspection request channel.
- The **INSPECTOR** checks one job at a time and sends the result via the inspection result channel.
- If inspection fails, the **DISPATCHER** sends a rework order via the rework channel. The worker must redo the failed job (re-use the workstation and tool if needed).
- If inspection passes, the worker proceeds to the next job or terminates if both jobs are done.
- The rework loop continues until all jobs pass inspection.

## Properties (verified by TLC)

- Safety: All 3 station mutual exclusion (each workstation used by at most one worker at a time). **TOOL_CABINET** counter never goes negative (at most 2 tools in use simultaneously).
- Liveness: All agents eventually terminate (all jobs completed and inspected). All shared resources freed. Counter returns to initial value (all tools returned). All channels drained.
