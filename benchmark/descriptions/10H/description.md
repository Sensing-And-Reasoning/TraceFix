# Task 10H: Four Builders with Build Slots and Cascading Rebuilds

Four builders compile modules in parallel for a large project. They depend on overlapping subsets of four shared artifacts. The build system has limited capacity — only two builds can execute concurrently (**BUILD_SLOTS**, initial=2). An artifact **VALIDATOR** checks each build for consistency with the shared artifacts, and a **TEST_RUNNER** validates functionality. When any builder modifies a shared artifact, all builders depending on that artifact must rebuild — creating cascading rebuild chains.

## Agents

- **BUILDER_A**: compiles Module A, depends on **CORE_LIB** and **CONFIG**
- **BUILDER_B**: compiles Module B, depends on **CORE_LIB** and **DATA_MODELS**
- **BUILDER_C**: compiles Module C, depends on **DATA_MODELS** and **API_TYPES**
- **BUILDER_D**: compiles Module D, depends on **API_TYPES** and **CONFIG**
- **VALIDATOR**: checks that each compiled module is consistent with the current version of its dependencies
- **TEST_RUNNER**: runs functional tests on validated modules
- **INTEGRATOR**: links all four validated and tested modules into the final artifact

## Shared Resources

- **CORE_LIB**, **DATA_MODELS**, **API_TYPES**, **CONFIG**: shared build artifacts
- **BUILD_SLOTS** counter (initial=2, limits concurrent builds)

## Channels

- Artifact update channel (Builders -> Builders, notification of shared artifact changes)
- Validation request channel (Builders -> **VALIDATOR**)
- Validation result channel (**VALIDATOR** -> Builders, pass or fail)
- Build done channel (Builders -> **TEST_RUNNER**)
- Test result channel (**TEST_RUNNER** -> Builders / **INTEGRATOR**, pass or fail)

## Workflow

### BUILDER_A
1. Wait for a **BUILD_SLOTS** slot to become available, then occupy it
2. Use **CORE_LIB** and **CONFIG** to compile Module A
3. Free the **BUILD_SLOTS** slot after compilation finishes
4. If shared artifacts were modified, notify dependent builders
5. Send validation request to **VALIDATOR**
6. Wait for validation result; if fail, go back to step 1
7. Send build done to **TEST_RUNNER**
8. Wait for test result; if fail, go back to step 1

### BUILDER_B
1. Wait for a **BUILD_SLOTS** slot to become available, then occupy it
2. Use **CORE_LIB** and **DATA_MODELS** to compile Module B
3. Free the **BUILD_SLOTS** slot after compilation finishes
4. If shared artifacts were modified, notify dependent builders
5. Send validation request to **VALIDATOR**
6. Wait for validation result; if fail, go back to step 1
7. Send build done to **TEST_RUNNER**
8. Wait for test result; if fail, go back to step 1

### BUILDER_C
1. Wait for a **BUILD_SLOTS** slot to become available, then occupy it
2. Use **DATA_MODELS** and **API_TYPES** to compile Module C
3. Free the **BUILD_SLOTS** slot after compilation finishes
4. If shared artifacts were modified, notify dependent builders
5. Send validation request to **VALIDATOR**
6. Wait for validation result; if fail, go back to step 1
7. Send build done to **TEST_RUNNER**
8. Wait for test result; if fail, go back to step 1

### BUILDER_D
1. Wait for a **BUILD_SLOTS** slot to become available, then occupy it
2. Use **API_TYPES** and **CONFIG** to compile Module D
3. Free the **BUILD_SLOTS** slot after compilation finishes
4. If shared artifacts were modified, notify dependent builders
5. Send validation request to **VALIDATOR**
6. Wait for validation result; if fail, go back to step 1
7. Send build done to **TEST_RUNNER**
8. Wait for test result; if fail, go back to step 1

### VALIDATOR
1. Wait for validation request from a builder
2. Validate the compiled artifact against current dependency versions
3. Send validation result (pass or fail) to the builder
4. Repeat until all modules are validated

### TEST_RUNNER
1. Wait for build done from a builder
2. Run functional tests on the validated module
3. Send test result (pass or fail) to the builder and **INTEGRATOR**
4. Repeat until all modules pass

### INTEGRATOR
1. Wait for all four modules to be validated and tested
2. Link all four modules into the final artifact

## Constraints

- Each shared artifact (**CORE_LIB**, **DATA_MODELS**, **API_TYPES**, **CONFIG**) can only be accessed by one builder at a time.
- Overlapping dependencies create four pairwise races: **BUILDER_A**-**BUILDER_B** (**CORE_LIB**), **BUILDER_B**-**BUILDER_C** (**DATA_MODELS**), **BUILDER_C**-**BUILDER_D** (**API_TYPES**), **BUILDER_A**-**BUILDER_D** (**CONFIG**). This forms a ring of contention across the four builders.
- Only 2 build slots are available (**BUILD_SLOTS** counter, initial=2). A builder must occupy a build slot before starting compilation and free it after finishing. This limits concurrency — with 4 builders and 2 slots, at most 2 builds run simultaneously.
- When a builder modifies a shared artifact, it sends an artifact update notification. All other builders that depend on that artifact must rebuild. Cascading rebuilds are possible: if **BUILDER_B** rebuilds and modifies **DATA_MODELS**, **BUILDER_C** must also rebuild.
- The artifact **VALIDATOR** checks one module at a time. If validation fails (artifact was modified after compilation), the builder must rebuild.
- The **TEST_RUNNER** tests one module at a time. If tests fail, the builder must rebuild.
- The **INTEGRATOR** cannot begin until all four modules are validated and tested.
- All four builders start concurrently and compete for build slots and shared artifacts.

## Properties (verified by TLC)

- Safety: All 4 artifact mutual exclusion (each artifact accessed by at most one builder at a time). **BUILD_SLOTS** counter never goes negative (at most 2 concurrent builds).
- Liveness: All agents eventually terminate (all four modules compiled, validated, tested, and linked). All resources released. Counter returns to initial value (all build slots freed). All channels drained. No deadlock.
