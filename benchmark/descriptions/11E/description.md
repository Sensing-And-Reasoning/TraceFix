# Task 11E: Two Technicians, Two Workstations

A workshop has two workstations (a **LATHE** and a **MILL**) and two technicians. Each technician must complete two independent jobs: one requires the **LATHE** and the other requires the **MILL**. When a workstation is occupied by the other technician, the technician works on the job requiring the other workstation instead of waiting. A **SUPERVISOR** collects completion reports from both technicians.

## Agents

- **TECHNICIAN_A**: must complete two jobs — one on the **LATHE** and one on the **MILL**. Can choose which job to do first based on workstation availability.
- **TECHNICIAN_B**: must complete two jobs — one on the **LATHE** and one on the **MILL**. Can choose which job to do first based on workstation availability.
- **SUPERVISOR**: collects job completion reports from both technicians (4 total: 2 per technician) and then terminates.

## Shared Resources

- **LATHE** workstation (can only be used by one technician at a time)
- **MILL** workstation (can only be used by one technician at a time)

## Workflow

### TECHNICIAN_A
- Chooses an available workstation. If both **LATHE** and **MILL** are available, the choice is nondeterministic. If one is occupied, uses the other workstation.
- Uses the chosen workstation, completes the job, and reports completion to the **SUPERVISOR** via the job done channel.
- After the first job, does the remaining job on the other workstation (only one action — no choice).

### TECHNICIAN_B
- Chooses an available workstation. If both **LATHE** and **MILL** are available, the choice is nondeterministic. If one is occupied, uses the other workstation.
- Uses the chosen workstation, completes the job, and reports completion to the **SUPERVISOR** via the job done channel.
- After the first job, does the remaining job on the other workstation (only one action — no choice).

### SUPERVISOR
- Waits for all 4 job-done messages before terminating.

## Constraints

- Each workstation (**LATHE**, **MILL**) can only be used by one technician at a time.
- Each technician has two independent jobs requiring different workstations. The jobs have no ordering dependency — either can be done first.
- When a technician is ready to start work, they choose an available workstation. If both are available, the choice is nondeterministic. If one is occupied, the technician works on the job requiring the other workstation.
- After completing a job, the technician reports completion to the **SUPERVISOR** via the job done channel.
- After the first job, the technician must do the remaining job on the other workstation (only one action — no choice).
- The **SUPERVISOR** waits for all 4 job-done messages before terminating.

## Properties (verified by TLC)

- Safety: **LATHE** mutual exclusion (only one technician uses the **LATHE** at a time). **MILL** mutual exclusion (only one technician uses the **MILL** at a time).
- Liveness: All agents eventually terminate (both technicians complete both jobs, **SUPERVISOR** receives all reports). All shared resources freed. All channel messages consumed.
