# Shared Codebase Development — 3 Agents

Three developers work in parallel on independent features in a shared codebase. The codebase contains 3 modules (auth, database, api). Multiple developers may need to modify the same module, but only one developer can modify a module at a time.

## Agents
- **DEVELOPER_A**: Building user authentication. Needs to modify **AUTH_MODULE** and **DATABASE_MODULE**.
- **DEVELOPER_B**: Building REST API endpoints. Needs to modify **DATABASE_MODULE** and **API_MODULE**.
- **DEVELOPER_C**: Building API auth middleware. Needs to modify **API_MODULE** and **AUTH_MODULE**.

## Shared Resources
- **AUTH_MODULE**: Authentication module
- **DATABASE_MODULE**: Database module
- **API_MODULE**: API module

## Workflow

Each developer first designs and implements their feature locally. When ready, they commit their changes to the required modules, then run local tests. If tests fail, the developer reports the failure and finishes.

## Goal
All three developers complete their work (design, implement, commit, test) without conflicts over shared modules.
