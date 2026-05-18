# Task 10M: Three Builders with Overlapping Dependencies

Three builders are compiling modules in parallel. Their modules depend on overlapping subsets of three shared artifacts, creating pairwise resource contention. Any builder that modifies a shared artifact must notify all other builders that depend on it, forcing them to rebuild. A **TEST_RUNNER** validates each completed build, and an **INTEGRATOR** links all validated modules.

## Agents

- **BUILDER_A**: compiles Module A, depends on **CORE_LIB** and **CONFIG**
- **BUILDER_B**: compiles Module B, depends on **CORE_LIB** and **DATA_MODELS**
- **BUILDER_C**: compiles Module C, depends on **DATA_MODELS** and **CONFIG**
- **TEST_RUNNER**: validates each compiled module before it can be accepted
- **INTEGRATOR**: links all three validated modules into the final artifact

## Shared Resources

- **CORE_LIB**: shared core library
- **DATA_MODELS**: shared data model definitions
- **CONFIG**: shared configuration artifact

## Channels

- Artifact update channel (Builders -> Builders, notification that a shared artifact has changed)
- Build done channel (Builders -> **TEST_RUNNER**)
- Test result channel (**TEST_RUNNER** -> Builders / **INTEGRATOR**, pass or rebuild)

## Workflow

### BUILDER_A
1. Use **CORE_LIB** and **CONFIG** to compile Module A
2. If shared artifacts were modified, notify dependent builders
3. Send build done to **TEST_RUNNER**
4. Wait for test result; if rebuild required, go back to step 1

### BUILDER_B
1. Use **CORE_LIB** and **DATA_MODELS** to compile Module B
2. If shared artifacts were modified, notify dependent builders
3. Send build done to **TEST_RUNNER**
4. Wait for test result; if rebuild required, go back to step 1

### BUILDER_C
1. Use **DATA_MODELS** and **CONFIG** to compile Module C
2. If shared artifacts were modified, notify dependent builders
3. Send build done to **TEST_RUNNER**
4. Wait for test result; if rebuild required, go back to step 1

### TEST_RUNNER
1. Wait for build done from a builder
2. Run build tests on the submitted module
3. Send test result (pass or rebuild) to the builder and **INTEGRATOR**
4. Repeat until all modules pass

### INTEGRATOR
1. Wait for all three modules to be tested and accepted
2. Link all three validated modules into the final artifact

## Constraints

- Each shared artifact (**CORE_LIB**, **DATA_MODELS**, **CONFIG**) can only be accessed by one builder at a time.
- Builders have overlapping dependencies: **BUILDER_A** and **BUILDER_B** both need **CORE_LIB**, **BUILDER_B** and **BUILDER_C** both need **DATA_MODELS**, **BUILDER_A** and **BUILDER_C** both need **CONFIG**. This creates three pairwise races.
- When a builder modifies a shared artifact during compilation, it must notify all other builders that depend on that artifact via the artifact update channel. Affected builders must rebuild.
- The **TEST_RUNNER** can only test one module at a time. A module must pass testing before the **INTEGRATOR** accepts it.
- The **INTEGRATOR** cannot begin linking until all three modules are tested and accepted.
- All three builders run concurrently from the start.

## Properties (verified by TLC)

- Safety: All 3 artifacts mutual exclusion (each artifact accessed by at most one builder at a time).
- Liveness: All agents eventually terminate (all modules compiled, tested, and linked). All resources released. All channels drained. No deadlock.
