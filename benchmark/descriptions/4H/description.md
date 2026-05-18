# Task 4H: Microservice Migration with Continuous Availability

A team is migrating a monolithic application into three microservices. The migration must happen without taking the system offline -- the existing system must continue serving users throughout the process.

## Agents

- **ARCHITECT**: designs the migration plan, defines service boundaries, approves each migration phase
- **DEVELOPER_A**: responsible for extracting and building microservice A
- **DEVELOPER_B**: responsible for extracting and building microservice B
- **DEVELOPER_C**: responsible for extracting and building microservice C
- **TESTER**: validates each microservice and the system as a whole at each migration phase
- **REVIEWER**: reviews code changes for each microservice before deployment approval
- **DEVOPS**: manages the deployment pipeline, service registry, and database migrations

## Shared Resources

- **TEST_ENV**: test environment for pre-deployment validation; only one test session can run at a time
- **STAGING_ENV**: staging environment for deployment and integration testing; only one deployment can proceed at a time

## Workflow

**ARCHITECT** designs the migration plan and communicates service boundaries and dependency ordering to the developers. Each developer (A, B, C) extracts and builds their microservice, then submits code for review by **REVIEWER**. The reviewer approves or requests changes before deployment. Once approved, the developer coordinates with **DEVOPS** for deployment. **TESTER** validates each microservice in **TEST_ENV** before deployment proceeds. **DEVOPS** deploys services to **STAGING_ENV**, runs database migrations, and registers services in the service registry. If a deployment fails, **DEVOPS** rolls back the service and notifies all affected agents; the responsible developer must fix the issue and re-enter the review and test cycle. Each microservice may depend on others, so the team must respect dependency ordering: a service that others depend on must be deployed first. The service registry must be updated to reflect the current state at all times.

## Goal

All agents complete their work (design, implementation, review, testing, deployment) without conflicts over shared resources, maintaining system availability throughout the migration.
