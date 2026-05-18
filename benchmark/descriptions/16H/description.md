# CI/CD Pipeline with Blue-Green and Canary Deployment

Seven engineers coordinate to build, test, and deploy a microservices application through a complex pipeline with security review, database migration, and blue-green/canary deployment. They share six pieces of infrastructure and a limited number of canary traffic slots.

## Agents
- **BUILD_MASTER**: orchestrates the pipeline, collects status reports, makes stage-gate decisions
- **FRONTEND_DEV**: compiles, tests, and publishes the frontend service
- **BACKEND_DEV**: compiles, tests, and publishes the backend service
- **DB_ADMIN**: performs database migration that must complete before service deployment
- **QA_ENGINEER**: runs integration and end-to-end tests
- **RELEASE_ENGINEER**: manages blue-green swap and canary traffic rollout
- **SECURITY_REVIEWER**: reviews each component for vulnerabilities; can reject, requiring rebuild

## Shared Resources
- **BUILD_SERVER**: CI build server for compilation and unit testing
- **ARTIFACT_STORE**: container/package registry for build artifacts
- **TEST_ENV**: staging environment for integration testing
- **STAGING_ENV**: pre-production environment for deployment validation
- **PROD_BLUE**: production environment Blue
- **PROD_GREEN**: production environment Green
- **CANARY_SLOTS**: shared pool of 3 traffic-routing slots (Counter, initial=3). Each slot represents 33% of production traffic. The **RELEASE_ENGINEER** uses slots incrementally during canary rollout (33% → 66% → 100%). If canary metrics fail at any stage, all used slots are returned and the deployment is rolled back.

## Communication Channels
- **BUILD_MASTER → FRONTEND_DEV**: build request, revision/rebuild request, standby notice, pipeline-complete notification
- **BUILD_MASTER → BACKEND_DEV**: build request, revision/rebuild request, standby notice, pipeline-complete notification
- **BUILD_MASTER → SECURITY_REVIEWER**: security review request, pipeline-complete notification
- **BUILD_MASTER → DB_ADMIN**: migration request, pipeline-complete notification
- **BUILD_MASTER → QA_ENGINEER**: test request, pipeline-complete notification
- **BUILD_MASTER → RELEASE_ENGINEER**: deploy request, pipeline-complete notification
- **FRONTEND_DEV → BUILD_MASTER**: build-success report, build-failed report
- **BACKEND_DEV → BUILD_MASTER**: build-success report, build-failed report
- **SECURITY_REVIEWER → BUILD_MASTER**: security verdict (approve or reject with components)
- **DB_ADMIN → BUILD_MASTER**: migration-complete report, migration-failed report
- **QA_ENGINEER → BUILD_MASTER**: test-passed report, test-failed report
- **RELEASE_ENGINEER → BUILD_MASTER**: staging report, production deployment report

## Workflow

### BUILD_MASTER
The **BUILD_MASTER** sends build requests to both the **FRONTEND_DEV** and **BACKEND_DEV** simultaneously. The **BUILD_MASTER** collects build reports from both developers in whatever order they arrive. If either build failed, the **BUILD_MASTER** sends revision requests to the failed developer(s) and standby notices to successful ones, then re-collects reports.

After both builds pass, the **BUILD_MASTER** sends a security review request to the **SECURITY_REVIEWER**. The **BUILD_MASTER** receives the security verdict. If security rejects any component, the **BUILD_MASTER** sends rebuild requests to the affected developer(s), re-collects build reports, and re-submits for security review. (At most one security revision cycle.)

After security approval, the **BUILD_MASTER** sends a migration request to the **DB_ADMIN** and waits for the migration report. If migration failed, the **BUILD_MASTER** sends a pipeline-complete notification to all agents and is done. If migration succeeded, the **BUILD_MASTER** sends a test request to the **QA_ENGINEER**.

The **BUILD_MASTER** receives the QA report. If QA failed, the **BUILD_MASTER** sends revision requests to the responsible developer(s) and re-collects, then sends a new test request. (At most one QA revision cycle.)

After QA passes, the **BUILD_MASTER** sends a deploy request to the **RELEASE_ENGINEER**. The **BUILD_MASTER** receives deployment reports and sends a pipeline-complete notification to all six other agents.

### FRONTEND_DEV
The **FRONTEND_DEV** receives a build request. The **FRONTEND_DEV** uses the **BUILD_SERVER** to compile the code and run unit tests — compilation can fail. If tests pass, the **FRONTEND_DEV** (still using the **BUILD_SERVER**) publishes the build artifact to the **ARTIFACT_STORE**. After publishing, the **FRONTEND_DEV** sends a build-success report. On failure, the **FRONTEND_DEV** sends a build-failed report.

On revision/rebuild requests, the **FRONTEND_DEV** repeats the cycle. The **FRONTEND_DEV** receives the pipeline-complete notification and is done.

### BACKEND_DEV
Same workflow as the **FRONTEND_DEV** but for the backend service.

### DB_ADMIN
The **DB_ADMIN** receives a migration request from the **BUILD_MASTER**. The **DB_ADMIN** uses the **BUILD_SERVER** to generate migration scripts. The **DB_ADMIN** then uses the **STAGING_ENV** to run a test migration — the migration can fail. If the test migration succeeds, the **DB_ADMIN** sends a migration-complete report to the **BUILD_MASTER**. If the test migration fails, the **DB_ADMIN** sends a migration-failed report to the **BUILD_MASTER**.

The **DB_ADMIN** receives the pipeline-complete notification and is done.

### QA_ENGINEER
The **QA_ENGINEER** receives a test request from the **BUILD_MASTER**. The **QA_ENGINEER** uses the **ARTIFACT_STORE** to pull artifacts. After pulling, the **QA_ENGINEER** uses the **TEST_ENV** to run integration tests — tests can fail — and end-to-end tests — tests can fail. The **QA_ENGINEER** sends the test report.

The **QA_ENGINEER** receives the pipeline-complete notification and is done.

### RELEASE_ENGINEER
The **RELEASE_ENGINEER** receives a deploy request from the **BUILD_MASTER**. The **RELEASE_ENGINEER** uses the **ARTIFACT_STORE** to pull production-ready artifacts, then proceeds.

The **RELEASE_ENGINEER** uses the **STAGING_ENV** to perform a staging deployment and run smoke tests — smoke tests can fail. If staging fails, the **RELEASE_ENGINEER** sends a staging-failed report. If staging succeeds, the **RELEASE_ENGINEER** proceeds to the blue-green canary rollout.

Assuming **PROD_BLUE** is the live environment and **PROD_GREEN** is standby, the **RELEASE_ENGINEER** begins the rollout:
1. The **RELEASE_ENGINEER** uses **PROD_GREEN** to deploy the new version and run smoke tests — can fail. If smoke tests fail, the **RELEASE_ENGINEER** sends a deploy-failed report.
2. On success, the **RELEASE_ENGINEER** takes one slot from **CANARY_SLOTS** (33% traffic to **PROD_GREEN**) and runs smoke tests on the canary — can fail. If canary fails, return the slot, stop using **PROD_GREEN**, and send a deploy-failed report (cascading rollback).
3. On success, take a second slot from **CANARY_SLOTS** (66% traffic). Run smoke tests — can fail. On failure, return both slots, stop using **PROD_GREEN**, and send a deploy-failed report.
4. On success, take the third slot from **CANARY_SLOTS** (100% traffic). The **RELEASE_ENGINEER** uses **PROD_BLUE** to drain remaining connections, then stops using **PROD_BLUE** (blue is now standby). Return all three slots (traffic fully on **PROD_GREEN**). Send a deploy-success report.

The **RELEASE_ENGINEER** receives the pipeline-complete notification and is done.

### SECURITY_REVIEWER
The **SECURITY_REVIEWER** receives a security review request from the **BUILD_MASTER**. The **SECURITY_REVIEWER** uses the **ARTIFACT_STORE** to pull and inspect build artifacts, then runs a security scan on each component — the scan can fail (vulnerability found). The **SECURITY_REVIEWER** sends the security verdict (approve all, or reject specific components) to the **BUILD_MASTER**.

The **SECURITY_REVIEWER** receives the pipeline-complete notification and is done.

## Goal
All seven engineers complete their work: the **BUILD_MASTER** communicates the pipeline result, both developers publish passing artifacts, the **DB_ADMIN** completes the migration, the **QA_ENGINEER** delivers passing tests, the **RELEASE_ENGINEER** completes the blue-green canary deployment, and the **SECURITY_REVIEWER** approves all components.
