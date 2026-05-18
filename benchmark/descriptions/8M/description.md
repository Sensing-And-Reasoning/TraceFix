# Task 8M: Full-Stack API Development

A team is building a full-stack feature that spans the **DATABASE**, backend API, and frontend UI. The three layers have strong sequential dependencies: the **DATABASE** schema must be ready before the backend can implement endpoints, and the backend API must be ready before the frontend can integrate. A tester validates the integrated system, and a reviewer approves code at each layer.

## Agents

- **BACKEND_DEV**: implements API endpoints, defines the API specification, depends on **DATABASE** schema being ready
- **FRONTEND_DEV**: implements the user interface, depends on the API being ready and stable
- **DB_ADMIN**: designs and executes **DATABASE** schema migrations, the foundation for the entire feature
- **TESTER**: runs integration tests across all layers
- **REVIEWER**: reviews code changes for each layer before they can proceed to integration

## Shared Resources

- **API_GATEWAY**: shared API specification that all layers read and write
- **DATABASE**: shared database where schema migrations are applied
- **TEST_ENV**: shared environment for running integration tests

## Workflow

Each agent works on their layer of the feature. DB_ADMIN executes schema migrations and notifies BACKEND_DEV and FRONTEND_DEV when the schema is ready. BACKEND_DEV implements API endpoints and defines the API specification after the schema is ready, then submits code for REVIEWER approval, and notifies FRONTEND_DEV and TESTER when the API is ready. FRONTEND_DEV implements the user interface after the API is ready and submits code for REVIEWER approval. REVIEWER reviews code changes for each layer and approves or requests changes; if API spec changes are requested, FRONTEND_DEV must be notified. TESTER runs integration tests across all layers and reports results to all developers. If tests fail, the responsible layer must fix the issue, potentially triggering cascading updates through the dependency chain.

## Constraints

- The **API_GATEWAY** specification can only be modified by one agent at a time. Both BACKEND_DEV and FRONTEND_DEV may need to read or update it.
- Only one schema change may run at a time.
- Only one test session may run at a time.
- Three-layer dependency chain: DB schema -> Backend API -> Frontend UI. BACKEND_DEV cannot finalize its API until the schema is ready. FRONTEND_DEV cannot integrate until the API is ready.
- If BACKEND_DEV discovers the schema is insufficient during implementation, DB_ADMIN must run an additional migration -- but this requires re-validating any backend code that was already written against the old schema.
- REVIEWER must approve each layer's code. If REVIEWER requests changes to the backend API that alter the specification, FRONTEND_DEV must be notified.
- If integration tests fail, the responsible layer must fix the issue, potentially triggering cascading updates through the dependency chain.

## Properties (verified by TLC)

- Safety: API_GATEWAY specification, DATABASE migration, and TEST_ENV mutual exclusion.
- Liveness: All agents eventually terminate (all layers implemented, reviewed, integrated, tested). All resources released. All channels drained. No deadlock (especially: the three-layer dependency chain does not deadlock if an upstream change triggers downstream re-work).
