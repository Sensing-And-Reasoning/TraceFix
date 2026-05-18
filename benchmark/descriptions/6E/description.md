# Task 6E: Shared Utility File Conflict

Two developers are implementing separate features in the same codebase. Both features require modifications to the shared code repository. A reviewer must approve each feature's changes before they can be merged into the main branch.

## Agents

### DEVELOPER_A
Implements a user authentication feature, needs to add helper functions to the shared utility file in **REPO**.

### DEVELOPER_B
Implements a notification feature, needs to modify existing functions in the shared utility file in **REPO**.

### REVIEWER
Reviews completed feature code and approves or requests changes before merge.

## Shared Resources
- **REPO**: code repository with shared files

## Workflow

Each developer implements their assigned feature, modifying the shared utility file in **REPO**. When ready, the developer notifies **REVIEWER** via the **code ready channel** that the feature is ready for review. **REVIEWER** reviews the submitted code and sends approval or a revision request back via the **review feedback channel**. If approved, the developer merges the feature into the main branch. If revision is requested, the developer revises and resubmits for review.

**REVIEWER** processes each feature in turn, repeating the review cycle until all features are approved and merged.

## Communication Channels
- **Code ready channel** (**DEVELOPER_A** / **DEVELOPER_B** -> **REVIEWER**, notification that code is ready for review)
- **Review feedback channel** (**REVIEWER** -> **DEVELOPER_A** / **DEVELOPER_B**, approval or revision request)

## Properties (verified by TLC)
- Safety: **REPO** is used by at most one agent at a time.
- Liveness: All agents eventually terminate (both features implemented, reviewed, and merged). All channel messages consumed. No deadlock.
