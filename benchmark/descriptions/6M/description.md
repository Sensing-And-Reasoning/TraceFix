# Task 6M: Multi-File Feature Development

Two developers are implementing features that share multiple source files. Their features touch overlapping parts of the codebase — shared utility files, data models, and configuration files all within the code repository. A test writer creates tests for completed features, a reviewer gates code quality, and a CI runner validates that all tests pass before merge.

## Agents

### DEVELOPER_A
Implements user authentication, modifies auth-specific files plus shared utility file and config file in **REPO**.

### DEVELOPER_B
Implements payment processing, modifies payment-specific files plus shared utility file and data models file in **REPO**.

### TEST_WRITER
Writes and runs tests for completed features in **TEST_ENV** — must read the feature code before writing tests.

### REVIEWER
Reviews code changes before they can be merged.

### CI_RUNNER
Runs the full test suite on **BUILD_SERVER** after each merge to detect integration issues.

## Shared Resources
- **REPO**: code repository with shared files
- **TEST_ENV**: test environment
- **BUILD_SERVER**: build server

## Workflow

Each developer implements their assigned feature in **REPO**, modifying shared files as needed. If an interface change affects the data models, the developer notifies the other developer via the **interface change channel**. When the feature is ready, the developer notifies **TEST_WRITER** via the **code ready channel** and submits for review via the **review request channel**.

**TEST_WRITER** waits for a code ready notification, then uses **TEST_ENV** to write and run tests for the completed feature. **TEST_WRITER** repeats this for each feature.

**REVIEWER** waits for review requests, reviews the submitted code, and sends approval or a revision request back via the **review feedback channel**. If approved, the developer merges the feature into **REPO**. If revision is requested, the developer revises and resubmits.

**CI_RUNNER** runs the full test suite on **BUILD_SERVER** after each merge and sends results via the **test result channel**. If CI fails, the developer who merged must fix the regression before the next merge can proceed.

## Communication Channels
- **Interface change channel** (**DEVELOPER_A** <-> **DEVELOPER_B**, notification of interface changes)
- **Code ready channel** (**DEVELOPER_A** / **DEVELOPER_B** -> **TEST_WRITER**, notification that feature code is complete)
- **Review request channel** (**DEVELOPER_A** / **DEVELOPER_B** -> **REVIEWER**, request for code review)
- **Review feedback channel** (**REVIEWER** -> **DEVELOPER_A** / **DEVELOPER_B**, approval or revision requests)
- **Test result channel** (**CI_RUNNER** -> **DEVELOPER_A** / **DEVELOPER_B**, test suite results after merge)

## Properties (verified by TLC)
- Safety: **REPO**, **TEST_ENV**, and **BUILD_SERVER** are each used by at most one agent at a time.
- Liveness: All agents eventually terminate (both features implemented, tested, reviewed, merged, CI passed). All channels drained. No deadlock.
