# Task 8E: Backend-Database Schema Sync

A backend developer is implementing a new feature that requires **DATABASE** schema changes. A DB admin manages schema migrations, and a tester validates the integrated result. The critical constraint is ordering: the **DATABASE** migration must complete before the backend code that depends on the new schema can be deployed and tested.

## Agents

- **BACKEND_DEV**: implements new API endpoints that depend on updated **DATABASE** schema (new tables or columns)
- **DB_ADMIN**: designs and executes **DATABASE** schema migrations
- **TESTER**: runs integration tests to validate that backend code works correctly with the new schema

## Shared Resources

- **DATABASE**: shared database where schema migrations are applied
- **TEST_ENV**: shared environment for running integration tests

## Workflow

Each agent works on their own part of the feature. DB_ADMIN executes schema migrations and notifies BACKEND_DEV when the migration is complete. BACKEND_DEV implements new API endpoints after the schema is ready. TESTER runs integration tests to validate that the backend works correctly with the updated schema and reports results to both BACKEND_DEV and DB_ADMIN. If tests fail, BACKEND_DEV reports the failure and finishes.

## Constraints

- Only one schema migration may run at a time (to prevent conflicting structural changes).
- BACKEND_DEV cannot deploy or test code that depends on new schema fields until the corresponding migration has been executed.
- Only one test session may run at a time.
- If tests fail, BACKEND_DEV reports the failure and finishes.

## Properties (verified by TLC)

- Safety: DATABASE mutual exclusion (only one migration at a time). TEST_ENV mutual exclusion (only one test session at a time).
- Liveness: All agents eventually terminate (migration applied, backend implemented, tests passed). All resources released. All channel messages consumed. No deadlock.
