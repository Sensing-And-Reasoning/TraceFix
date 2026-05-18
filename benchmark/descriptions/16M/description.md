# CI/CD Pipeline Orchestration

Five engineers coordinate to build, test, and deploy a microservices application consisting of a frontend and a backend. They share four pieces of infrastructure: a CI build server, a staging/test environment, an artifact registry, and the production environment.

## Agents
- **BUILD_MASTER**: orchestrates the overall pipeline, collects status reports, makes go/no-go decisions at each stage gate
- **FRONTEND_DEV**: compiles, unit-tests, and publishes the frontend service
- **BACKEND_DEV**: compiles, unit-tests, and publishes the backend service
- **QA_ENGINEER**: runs integration and end-to-end tests against a deployed staging environment
- **RELEASE_ENGINEER**: deploys artifacts to staging for QA validation, then promotes to production

## Shared Resources
- **BUILD_SERVER**: continuous integration build server for compilation and unit testing
- **ARTIFACT_STORE**: container/package registry for publishing and pulling build artifacts
- **TEST_ENV**: staging environment for integration testing and deployment validation
- **PROD_ENV**: production environment for live deployment

## Communication Channels
- **BUILD_MASTER → FRONTEND_DEV**: build request, revision request, standby notice, pipeline-complete notification
- **BUILD_MASTER → BACKEND_DEV**: build request, revision request, standby notice, pipeline-complete notification
- **BUILD_MASTER → QA_ENGINEER**: test request, pipeline-complete notification
- **BUILD_MASTER → RELEASE_ENGINEER**: deploy request, abort signal, promote signal, pipeline-complete notification
- **FRONTEND_DEV → BUILD_MASTER**: build-success report, build-failed report
- **BACKEND_DEV → BUILD_MASTER**: build-success report, build-failed report
- **QA_ENGINEER → BUILD_MASTER**: test-passed report, test-failed report
- **RELEASE_ENGINEER → BUILD_MASTER**: staging deployment report, production deployment report

## Workflow

### BUILD_MASTER
The **BUILD_MASTER** begins by sending build requests to both the **FRONTEND_DEV** and the **BACKEND_DEV** simultaneously.

The **BUILD_MASTER** then collects build reports from both developers in whatever order they arrive. After receiving both reports, the **BUILD_MASTER** evaluates the results. If either build failed, the **BUILD_MASTER** sends a revision request to the failed developer(s) and a standby notice to any developer that succeeded, then collects revised build reports. If both builds succeeded, the **BUILD_MASTER** proceeds.

After confirming both builds passed, the **BUILD_MASTER** sends a test request to the **QA_ENGINEER**.

The **BUILD_MASTER** then receives the QA test report. If QA failed, the **BUILD_MASTER** must decide which component caused the failure. The **BUILD_MASTER** sends a revision request to the responsible developer(s) — this may be one or both — and a standby notice to any developer not at fault. The **BUILD_MASTER** then collects revised build reports, and sends a new test request to the **QA_ENGINEER**. The **BUILD_MASTER** receives the new QA report. (For modeling purposes, at most one QA revision cycle occurs.)

After QA passes, the **BUILD_MASTER** sends a deploy request to the **RELEASE_ENGINEER**.

The **BUILD_MASTER** receives the staging deployment report from the **RELEASE_ENGINEER**. If staging failed, the **BUILD_MASTER** sends an abort signal to the **RELEASE_ENGINEER** and is done. If staging succeeded, the **BUILD_MASTER** sends a promote signal to the **RELEASE_ENGINEER**.

The **BUILD_MASTER** receives the final production deployment report from the **RELEASE_ENGINEER**. The **BUILD_MASTER** then sends a pipeline-complete notification to all four other agents and is done.

### FRONTEND_DEV
The **FRONTEND_DEV** receives a build request from the **BUILD_MASTER**. The **FRONTEND_DEV** uses the **BUILD_SERVER** to compile the frontend code and run unit tests. If compilation and tests pass, the **FRONTEND_DEV** (still using the **BUILD_SERVER**) publishes the build artifact to the **ARTIFACT_STORE**. The **FRONTEND_DEV** must use the **BUILD_SERVER** during publishing because the publish step reads build metadata (hashes, manifests) directly from the **BUILD_SERVER**'s workspace. After publishing, the **FRONTEND_DEV** sends a build-success report to the **BUILD_MASTER**.

If the unit tests fail, the **FRONTEND_DEV** sends a build-failed report to the **BUILD_MASTER**.

On receiving a revision request, the **FRONTEND_DEV** repeats the full build-test-publish cycle. On receiving a standby notice, the **FRONTEND_DEV** waits for the pipeline-complete notification.

The **FRONTEND_DEV** receives the pipeline-complete notification and is done.

### BACKEND_DEV
The **BACKEND_DEV** receives a build request from the **BUILD_MASTER**. The **BACKEND_DEV** uses the **BUILD_SERVER** to compile the backend code and run unit tests. If compilation and tests pass, the **BACKEND_DEV** (still using the **BUILD_SERVER**) publishes the build artifact to the **ARTIFACT_STORE** for the same workspace-dependency reason as the frontend. After publishing, the **BACKEND_DEV** sends a build-success report to the **BUILD_MASTER**.

If tests fail, the **BACKEND_DEV** sends a build-failed report.

On receiving a revision request, the **BACKEND_DEV** repeats the build cycle. On receiving a standby notice, the **BACKEND_DEV** waits for pipeline-complete.

The **BACKEND_DEV** receives the pipeline-complete notification and is done.

### QA_ENGINEER
The **QA_ENGINEER** receives a test request from the **BUILD_MASTER**. The **QA_ENGINEER** uses the **ARTIFACT_STORE** to pull the latest build artifacts into the test harness — the **ARTIFACT_STORE** must be used during the pull to guarantee a consistent snapshot (no partial publishes from a concurrent rebuild). After pulling artifacts, the **QA_ENGINEER** uses the **TEST_ENV** to deploy the artifacts, run integration tests, and run end-to-end tests. If either integration or E2E tests fail, the **QA_ENGINEER** sends a test-failed report to the **BUILD_MASTER**. If all tests pass, the **QA_ENGINEER** sends a test-passed report.

On a subsequent test request (after revision), the **QA_ENGINEER** repeats the full pull-deploy-test cycle.

The **QA_ENGINEER** receives the pipeline-complete notification and is done.

### RELEASE_ENGINEER
The **RELEASE_ENGINEER** receives a deploy request from the **BUILD_MASTER**. The **RELEASE_ENGINEER** uses the **ARTIFACT_STORE** to pull production-ready artifacts. After pulling, the **RELEASE_ENGINEER** uses the **TEST_ENV** to perform the staging deployment and run a staging smoke test. If the staging deployment or smoke test fails, the **RELEASE_ENGINEER** sends a staging-failed report to the **BUILD_MASTER**. If staging succeeds, the **RELEASE_ENGINEER** sends a staging-success report.

The **RELEASE_ENGINEER** then receives either an abort or a promote signal from the **BUILD_MASTER**. On abort, the **RELEASE_ENGINEER** is done.

On promote, the **RELEASE_ENGINEER** uses the **PROD_ENV** to deploy the artifacts to production and run a production smoke test. After the smoke test, the **RELEASE_ENGINEER** sends the final production report to the **BUILD_MASTER**.

The **RELEASE_ENGINEER** receives the pipeline-complete notification and is done.

## Goal
All five engineers complete their work: the **BUILD_MASTER** has communicated the pipeline result to everyone, both developers have published passing artifacts and received the pipeline-complete notification, the **QA_ENGINEER** has delivered a passing test report, and the **RELEASE_ENGINEER** has completed the production deployment.
