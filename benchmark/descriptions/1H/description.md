# Shared Codebase Development — 7 Agents

Seven developers work in parallel on independent features in a shared codebase. The codebase contains 7 modules (auth, database, api, payment, notify, analytics, search). Multiple developers may need to modify the same module, but only one developer can modify a module at a time.

## Agents
- **DEVELOPER_A**: Building user authentication. Needs to modify **AUTH_MODULE** and **DATABASE_MODULE**.
- **DEVELOPER_B**: Building REST API endpoints. Needs to modify **DATABASE_MODULE** and **API_MODULE**.
- **DEVELOPER_C**: Building the payment system. Needs to modify **API_MODULE** and **PAYMENT_MODULE**.
- **DEVELOPER_D**: Building the notification service. Needs to modify **PAYMENT_MODULE** and **NOTIFY_MODULE**.
- **DEVELOPER_E**: Building data analytics. Needs to modify **NOTIFY_MODULE** and **ANALYTICS_MODULE**.
- **DEVELOPER_F**: Building the search engine. Needs to modify **ANALYTICS_MODULE** and **SEARCH_MODULE**.
- **DEVELOPER_G**: Building the admin panel. Needs to modify **SEARCH_MODULE** and **AUTH_MODULE**.

## Shared Resources
- **AUTH_MODULE**: Authentication module
- **DATABASE_MODULE**: Database module
- **API_MODULE**: API module
- **PAYMENT_MODULE**: Payment module
- **NOTIFY_MODULE**: Notification module
- **ANALYTICS_MODULE**: Analytics module
- **SEARCH_MODULE**: Search module

## Workflow

Each developer first designs and implements their feature locally. When ready, they commit their changes to the required modules, then run local tests. If tests fail, the developer must fix the code locally and retry (re-implement, commit, and re-test) until tests pass.

## Goal
All seven developers successfully complete their work (design, implement, commit, test — with retry on failure) without conflicts over shared modules.
