# Task 4E: Frontend-Backend API Coordination

A **FRONTEND_DEV** developer and a **BACKEND_DEV** developer are building a feature that requires them to agree on an API contract. A **TESTER** validates the integrated feature once both sides are ready.

## Agents

- **FRONTEND_DEV**: implements the user-facing component that calls the **BACKEND_DEV** API
- **BACKEND_DEV**: implements the API endpoint that serves data to the **FRONTEND_DEV**
- **TESTER**: runs integration tests once both **FRONTEND_DEV** and **BACKEND_DEV** are ready

## Shared Resources

- **REPO**: shared code repository containing the API specification; only one agent can write to it at a time
- **TEST_ENV**: test environment for running integration tests; only one agent can use it at a time

## Workflow

**BACKEND_DEV** defines the API specification in **REPO**, then both **FRONTEND_DEV** and **BACKEND_DEV** implement their respective components. Neither developer begins implementation until the API contract is agreed upon. When both sides are ready, they notify **TESTER**, who runs integration tests in **TEST_ENV** and reports results back to both developers. If either developer needs to change the API spec after implementation has started, the other developer must be notified and may need to adapt their code.

## Goal

All three agents complete their work (API definition, implementation, testing) without conflicts over shared resources.
