# Task 11H: Production Line with Flexible Routing

A production line has four workstations, four workers, and shared resources (tools and raw materials). Each worker has multiple jobs that can be done on different subsets of workstations. When a workstation is occupied, a worker routes to an alternative workstation instead of waiting. Jobs consume raw materials and require tools. A quality **INSPECTOR** checks finished work, a **MATERIAL_HANDLER** replenishes resources on request, and a **PACKAGER** collects all finished goods.

## Agents

- **WORKER_A**: has 2 jobs. Job 1 can be done on **STATION_1** or **STATION_2** (alternative routing). Job 2 requires **STATION_3**. Each job consumes 1 raw material and requires 1 tool.
- **WORKER_B**: has 2 jobs. Job 1 can be done on **STATION_2** or **STATION_3** (alternative routing). Job 2 requires **STATION_4**. Each job consumes 1 raw material and requires 1 tool.
- **WORKER_C**: has 2 jobs. Job 1 can be done on **STATION_3** or **STATION_4** (alternative routing). Job 2 requires **STATION_1**. Each job consumes 1 raw material and requires 1 tool.
- **WORKER_D**: has 2 jobs. Job 1 can be done on **STATION_4** or **STATION_1** (alternative routing). Job 2 requires **STATION_2**. Each job consumes 1 raw material and requires 1 tool.
- **INSPECTOR**: receives inspection requests, checks quality, and sends pass/fail results. Failed jobs must be reworked.
- **MATERIAL_HANDLER**: receives material requests and replenishes **RAW_MATERIAL** (counter increment). Responds when materials run low.
- **PACKAGER**: collects all finished goods from workers (8 total: 2 per worker) and terminates.

## Shared Resources

- **STATION_1**, **STATION_2**, **STATION_3**, **STATION_4** workstations (each can only be used by one worker at a time)
- **TOOL_SUPPLY** counter (initial=3, shared tools returned after each job)
- **RAW_MATERIAL** counter (initial=4, consumed by each job, replenished by **MATERIAL_HANDLER**)

## Workflow

### WORKER_A
- For Job 1: chooses between **STATION_1** and **STATION_2** (nondeterministic if both available). Uses the station, takes a tool from **TOOL_SUPPLY**, and 1 unit of **RAW_MATERIAL**. Completes the job and returns the tool.
- For Job 2: uses **STATION_3**, a tool, and 1 unit of **RAW_MATERIAL**. Completes the job and returns the tool.
- After completing a job, sends an inspection request. If inspection fails, reworks the job. If inspection passes, sends the finished good to **PACKAGER**.
- If raw materials are depleted, sends a material request to **MATERIAL_HANDLER**.

### WORKER_B
- For Job 1: chooses between **STATION_2** and **STATION_3** (nondeterministic if both available). Uses the station, takes a tool from **TOOL_SUPPLY**, and 1 unit of **RAW_MATERIAL**. Completes the job and returns the tool.
- For Job 2: uses **STATION_4**, a tool, and 1 unit of **RAW_MATERIAL**. Completes the job and returns the tool.
- After completing a job, sends an inspection request. If inspection fails, reworks the job. If inspection passes, sends the finished good to **PACKAGER**.
- If raw materials are depleted, sends a material request to **MATERIAL_HANDLER**.

### WORKER_C
- For Job 1: chooses between **STATION_3** and **STATION_4** (nondeterministic if both available). Uses the station, takes a tool from **TOOL_SUPPLY**, and 1 unit of **RAW_MATERIAL**. Completes the job and returns the tool.
- For Job 2: uses **STATION_1**, a tool, and 1 unit of **RAW_MATERIAL**. Completes the job and returns the tool.
- After completing a job, sends an inspection request. If inspection fails, reworks the job. If inspection passes, sends the finished good to **PACKAGER**.
- If raw materials are depleted, sends a material request to **MATERIAL_HANDLER**.

### WORKER_D
- For Job 1: chooses between **STATION_4** and **STATION_1** (nondeterministic if both available). Uses the station, takes a tool from **TOOL_SUPPLY**, and 1 unit of **RAW_MATERIAL**. Completes the job and returns the tool.
- For Job 2: uses **STATION_2**, a tool, and 1 unit of **RAW_MATERIAL**. Completes the job and returns the tool.
- After completing a job, sends an inspection request. If inspection fails, reworks the job. If inspection passes, sends the finished good to **PACKAGER**.
- If raw materials are depleted, sends a material request to **MATERIAL_HANDLER**.

### INSPECTOR
- Receives inspection requests, checks quality, and sends pass/fail results via the inspection result channel.

### MATERIAL_HANDLER
- Receives material requests and replenishes **RAW_MATERIAL** (counter increment). Responds when materials run low.

### PACKAGER
- Collects all 8 finished goods (2 per worker) via the packaging channel and terminates.

## Constraints

- Each workstation can only be used by one worker at a time.
- Workers have overlapping station alternatives forming a ring: **WORKER_A** uses **STATION_1**/**STATION_2**, **WORKER_B** uses **STATION_2**/**STATION_3**, **WORKER_C** uses **STATION_3**/**STATION_4**, **WORKER_D** uses **STATION_4**/**STATION_1**. This creates four pairwise contention points.
- The **TOOL_SUPPLY** has 3 tools (Counter, initial=3). Each job requires 1 tool during execution. The tool is returned after the job completes.
- **RAW_MATERIAL** starts at 4 units (Counter, initial=4). Each job consumes 1 unit. With 8 total jobs and only 4 initial units, workers must request replenishment from the **MATERIAL_HANDLER** partway through.
- When a worker's job consumes the last raw material (or materials are depleted), the worker sends a material request to the **MATERIAL_HANDLER**, who replenishes the supply.
- After completing a job, the worker sends an inspection request. If inspection fails, the worker must rework the job (re-use the station, tool, and raw material).
- After passing inspection, the worker sends the finished good to the **PACKAGER** via the packaging channel.
- The **PACKAGER** waits for all 8 finished goods before terminating.

## Properties (verified by TLC)

- Safety: All 4 station mutual exclusion (each workstation used by at most one worker at a time). **TOOL_SUPPLY** counter never goes negative (at most 3 tools in use simultaneously). **RAW_MATERIAL** counter never goes negative.
- Liveness: All agents eventually terminate (all 8 jobs completed, inspected, and packaged). All shared resources freed. All counters stable (tools returned; raw materials consumed but replenished as needed). All channels drained.
