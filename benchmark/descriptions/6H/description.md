# Task 6H: Parallel Feature Development with Staged Integration

Three developers are implementing features for a coordinated release. Their features share multiple source files in the code repository and have integration dependencies. A test writer validates features, a reviewer gates code quality, a CI runner checks integration on the build server, and a release manager coordinates the staged deployment through the staging environment.

## Agents

### DEVELOPER_A
Implements user authentication — modifies auth files, shared utility file, config file in **REPO**.

### DEVELOPER_B
Implements payment processing — modifies payment files, shared utility file, data models file, API types file in **REPO**.

### DEVELOPER_C
Implements notification system — modifies notification files, data models file, config file, API types file in **REPO**.

### TEST_WRITER
Creates and runs tests for completed features in **TEST_ENV** before review.

### REVIEWER
Reviews all code changes, approves or requests revisions.

### CI_RUNNER
Runs the full test suite on **BUILD_SERVER** after merges, validates integration.

### RELEASE_MANAGER
Coordinates staged deployment through **STAGING_ENV**, can trigger rollback if staging validation fails.

## Shared Resources
- **REPO**: code repository with shared files
- **TEST_ENV**: test environment
- **BUILD_SERVER**: build server
- **STAGING_ENV**: staging environment

## Workflow

Each developer implements their assigned feature in **REPO**, modifying shared files as needed. If an interface change affects shared files, the developer notifies other developers via the **interface change channel**. When ready, the developer notifies **TEST_WRITER** via the **code ready channel** and submits for review via the **review request channel**.

**TEST_WRITER** waits for a code ready notification, then uses **TEST_ENV** to write and run tests for the completed feature. **TEST_WRITER** repeats this for each feature.

**REVIEWER** waits for review requests, reviews the submitted code, and sends approval or a revision request back via the **review feedback channel**. If approved, the developer merges the feature into **REPO**. If revision is requested, the developer revises and resubmits.

**CI_RUNNER** runs the full test suite on **BUILD_SERVER** after each merge and sends results via the **test result channel** to the developers and **RELEASE_MANAGER**. If CI fails, the developer who merged must fix the regression before the next merge can proceed.

**RELEASE_MANAGER** receives CI results via the **test result channel** and, for each successfully merged feature, deploys it to **STAGING_ENV** using `deploy_service`, then validates the deployment using `validate_staging`. If staging validation passes, **RELEASE_MANAGER** approves the release via the **release approval channel**. If validation fails, **RELEASE_MANAGER** triggers a rollback using `rollback_service` and sends a rollback notification via the **rollback channel**; the responsible developer must fix and re-enter the review cycle. Features must be deployed in order: Feature A (user authentication) before Feature B (payment processing), and Feature B before Feature C (notification system).

## Communication Channels
- **Interface change channel** (**DEVELOPER_A** / **DEVELOPER_B** / **DEVELOPER_C** <-> each other, notification of shared file changes)
- **Code ready channel** (**DEVELOPER_A** / **DEVELOPER_B** / **DEVELOPER_C** -> **TEST_WRITER**)
- **Review request channel** (**DEVELOPER_A** / **DEVELOPER_B** / **DEVELOPER_C** -> **REVIEWER**)
- **Review feedback channel** (**REVIEWER** -> **DEVELOPER_A** / **DEVELOPER_B** / **DEVELOPER_C**)
- **Test result channel** (**CI_RUNNER** -> **DEVELOPER_A** / **DEVELOPER_B** / **DEVELOPER_C** / **RELEASE_MANAGER**)
- **Release approval channel** (**RELEASE_MANAGER** -> **DEVELOPER_A** / **DEVELOPER_B** / **DEVELOPER_C**, staged deployment approval)
- **Rollback channel** (**RELEASE_MANAGER** -> **DEVELOPER_A** / **DEVELOPER_B** / **DEVELOPER_C** / **CI_RUNNER**, rollback trigger)

## Properties (verified by TLC)
- Safety: **REPO**, **TEST_ENV**, **BUILD_SERVER**, and **STAGING_ENV** are each used by at most one agent at a time.
- Liveness: All agents eventually terminate (all features developed, reviewed, merged, CI passed, staging validated, released). All channels drained. No deadlock.
