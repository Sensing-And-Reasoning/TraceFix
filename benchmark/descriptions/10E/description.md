# Task 10E: Two Builders with Shared Library

Two builders are compiling modules in parallel for a software project. Both modules depend on a shared core library that can only be compiled against by one builder at a time. **BUILDER_A** also maintains a shared type definitions file that **BUILDER_B** depends on. An **INTEGRATOR** links the final artifacts after both builders finish.

## Agents

- **BUILDER_A**: compiles Module A, which depends on **CORE_LIB** and produces updates to **SHARED_TYPES**
- **BUILDER_B**: compiles Module B, which depends on both **CORE_LIB** and **SHARED_TYPES**
- **INTEGRATOR**: links both compiled modules into the final artifact

## Shared Resources

- **CORE_LIB**: shared core library
- **SHARED_TYPES**: shared type definitions file

## Channels

- Artifact update channel (**BUILDER_A** -> **BUILDER_B**, notifying that **SHARED_TYPES** has changed)
- Build done channel (**BUILDER_A** -> **INTEGRATOR**, **BUILDER_B** -> **INTEGRATOR**)

## Workflow

### BUILDER_A
1. Use **CORE_LIB** to compile Module A
2. Update the **SHARED_TYPES** definitions
3. Notify **BUILDER_B** that **SHARED_TYPES** has changed (artifact update channel)
4. Send build done to **INTEGRATOR**

### BUILDER_B
1. Use **CORE_LIB** to compile Module B
2. Read **SHARED_TYPES** definitions
3. If **BUILDER_A** updated **SHARED_TYPES** after **BUILDER_B** compiled against them, discard build and recompile
4. Send build done to **INTEGRATOR**

### INTEGRATOR
1. Wait for build done from both **BUILDER_A** and **BUILDER_B**
2. Link both compiled modules into the final artifact

## Constraints

- The core library (**CORE_LIB**) can only be read/compiled against by one builder at a time. Both builders need it during compilation.
- The shared type definitions file (**SHARED_TYPES**) can only be modified by one agent at a time. **BUILDER_A** writes new type definitions; **BUILDER_B** reads them during compilation.
- If **BUILDER_A** updates **SHARED_TYPES** after **BUILDER_B** has already compiled against them, **BUILDER_B** must discard its build and recompile with the updated types.
- The **INTEGRATOR** cannot begin linking until both builders have completed their current builds successfully.
- Both builders run concurrently from the start — the order in which they access shared resources is nondeterministic.

## Properties (verified by TLC)

- Safety: **CORE_LIB** mutual exclusion (never compiled against by two builders simultaneously). **SHARED_TYPES** mutual exclusion (never read and written simultaneously).
- Liveness: All agents eventually terminate (both modules compiled, final artifact linked). All resources released. All channels drained. No deadlock.
