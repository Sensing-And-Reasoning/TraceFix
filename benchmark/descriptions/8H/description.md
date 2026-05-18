# Task 8H: Multi-Service API Platform

A team is building a platform with two backend services and a frontend, all sharing a **DATABASE** and a common API specification. The two backend services have a dependency relationship (Service B calls Service A's endpoints). A DB admin manages the shared **DATABASE**, a tester validates integration, a reviewer approves code, and a DevOps engineer handles deployment with rollback capability.

## Agents

- **BACKEND_A**: implements Service A (user management), contributes to the shared API specification
- **BACKEND_B**: implements Service B (order processing), depends on Service A's endpoints, contributes to the shared API specification
- **FRONTEND_DEV**: implements the UI, depends on both services being ready
- **DB_ADMIN**: designs and executes **DATABASE** schema migrations for the shared **DATABASE**
- **TESTER**: runs integration tests in the **TEST_ENV**
- **REVIEWER**: reviews code changes for all services
- **DEV_OPS**: manages the deployment pipeline, service registry, and handles rollbacks

## Shared Resources

- **API_GATEWAY**: shared API specification used by both backend developers and frontend
- **DATABASE**: shared database where schema migrations are applied
- **TEST_ENV**: shared environment for running integration tests
- **STAGING_ENV**: shared deployment pipeline for staging service releases

## Workflow

Each agent works on their part of the platform. DB_ADMIN executes schema migrations and notifies BACKEND_A, BACKEND_B, and FRONTEND_DEV when the schema is ready. BACKEND_A implements Service A (user management) and contributes to the shared API specification after the schema is ready, submits code for REVIEWER approval, then requests deployment from DEV_OPS and notifies BACKEND_B when Service A is deployed and ready. BACKEND_B waits for both the schema and Service A to be ready before implementing Service B (order processing) and contributing to the shared API specification, submits code for REVIEWER approval, then requests deployment from DEV_OPS. FRONTEND_DEV waits for both services to be ready before implementing the UI, submits code for REVIEWER approval, then requests deployment from DEV_OPS. REVIEWER reviews code changes for all services and approves or requests changes. TESTER runs integration tests for each service and the full platform and reports results to all developers and DEV_OPS. DEV_OPS deploys services one at a time using `deploy_service`; after a successful deployment, DEV_OPS calls `register_service` to register the service in the service mesh. If a deployment fails, DEV_OPS calls `rollback_service` and sends rollback alerts to all affected developers. The deploy → register (on success) or deploy → rollback (on failure) decision is made per service.

## Constraints

- The **API_GATEWAY** specification is shared by both backend developers and FRONTEND_DEV. Only one agent can modify it at a time.
- Only one schema change may run at a time. Both services share the same **DATABASE**.
- Service B depends on Service A: Service A must be deployed and registered before Service B can be tested against it.
- The deployment pipeline (**STAGING_ENV**) processes one service at a time.
- The service registry (managed via **API_GATEWAY**) can only be updated by one agent at a time. A new service version must be registered before the old version is decommissioned.
- Only one test session may run at a time.
- If a deployment fails, DEV_OPS sends a rollback alert to all affected developers via the rollback alert channel. The service registry is updated to reflect the reverted state. The responsible developer must fix the issue and re-enter the review -> test -> deploy cycle. Dependent services may need to be re-tested.
- If BACKEND_B changes the API spec in a way that conflicts with BACKEND_A's endpoints, the conflict must be resolved before either can proceed.

## Properties (verified by TLC)

- Safety: All shared resources mutual exclusion (each held by at most one agent at a time).
- Liveness: All agents eventually terminate (both services and frontend deployed, tested, registered). All resources released. All channels drained. No deadlock (especially: service dependency ordering doesn't deadlock, API spec contention between two backend developers doesn't deadlock, rollback doesn't cause infinite retry loops).
