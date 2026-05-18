# Task 4M: Shared Library Refactoring with Code Review

Two developers are refactoring different modules in a codebase. Both modules depend on a shared utility library. An **ARCHITECT** oversees the design, a **REVIEWER** approves code changes, and a **TESTER** validates the results.

## Agents

- **ARCHITECT**: creates design proposals for each module refactoring, resolves conflicting design decisions
- **DEVELOPER_A**: refactors module A, which depends on the shared library
- **DEVELOPER_B**: refactors module B, which depends on the shared library
- **REVIEWER**: reviews code changes before they can be merged
- **TESTER**: runs the test suite to validate changes

## Shared Resources

- **REPO**: shared code repository containing the shared library and module code; only one agent can modify or merge into it at a time
- **TEST_ENV**: test environment for running test suites; only one agent can use it at a time

## Workflow

**ARCHITECT** creates a design proposal for each module refactoring before implementation begins. Once the design is ready, each developer refactors their module along with any shared library changes in **REPO**, then submits the code for review by **REVIEWER**. The reviewer approves or requests changes before merge. After approval, the developer merges into **REPO**. **TESTER** runs the test suite in **TEST_ENV** to validate the changes, and after any shared library modification, retests all dependent modules. **TESTER** reports results to the developers. All code changes must pass review before being merged.

## Goal

All agents complete their work (design approval, refactoring, review, testing, merge) without conflicts over shared resources.
