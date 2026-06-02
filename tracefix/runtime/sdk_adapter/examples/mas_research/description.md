# Research-brief MAS: future directions of LLM MAS verification

A multi-agent system that collaboratively researches the future research directions of
**verifying LLM multi-agent systems** and produces a single reviewed document.

## Agents

- **RESEARCHER_FM**, **RESEARCHER_RT**, **RESEARCHER_EVAL** — three research agents that work
  **concurrently**, each on a different direction:
  - `FM`   — formal methods / static verification of coordination protocols
  - `RT`   — runtime monitoring & enforcement of agent behavior
  - `EVAL` — benchmarks & evaluation methodology for MAS verification
  Each writes its own section into the **shared** document `research.md`.
- **PLOTTER** — once all three sections exist, adds an architecture / taxonomy figure to
  `research.md`.
- **CHECKER** — once all three sections exist, independently reads `research.md` and verifies
  the factual / quantitative claims, writing findings to `data_check.md`.
- **APPROVER** — once figures and data-check are both done, reads everything and writes the
  final acceptance verdict `ACCEPTANCE.md`.

## Shared resources & ordering constraints

- `research.md` is shared mutable state written by the three researchers **and** PLOTTER. They
  must never clobber each other's edits → a **mutual-exclusion lock `DOC`** serializes every
  write to it (read-modify-write while holding the lock).
- PLOTTER and CHECKER may only start after **all three** research sections are in place.
- APPROVER may only start after **both** PLOTTER (figures) and CHECKER (data verified) are done.

## Failure / edge behavior

Coordination must be deadlock-free and must terminate: every lock acquired is released before
the agent signals done, every message sent is eventually received, and no agent waits forever.
TraceFix verifies exactly these coordination-safety properties (it does not check the prose).
