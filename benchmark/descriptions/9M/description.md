# Task 9M: Five Dining Philosophers

Five philosophers sit around a circular table. Between each pair of adjacent philosophers lies a shared fork (5 forks total). Each philosopher alternates between thinking and eating. To eat, a philosopher must hold both adjacent forks simultaneously. After eating, the philosopher puts down both forks. All philosophers must eventually eat at least once and then finish.

## Agents

- **PHILOSOPHER_A**: sits between **FORK_A** (left) and **FORK_E** (right)
- **PHILOSOPHER_B**: sits between **FORK_B** (left) and **FORK_A** (right)
- **PHILOSOPHER_C**: sits between **FORK_C** (left) and **FORK_B** (right)
- **PHILOSOPHER_D**: sits between **FORK_D** (left) and **FORK_C** (right)
- **PHILOSOPHER_E**: sits between **FORK_E** (left) and **FORK_D** (right)

## Shared Resources

- **FORK_A** (shared between **PHILOSOPHER_A** and **PHILOSOPHER_B**)
- **FORK_B** (shared between **PHILOSOPHER_B** and **PHILOSOPHER_C**)
- **FORK_C** (shared between **PHILOSOPHER_C** and **PHILOSOPHER_D**)
- **FORK_D** (shared between **PHILOSOPHER_D** and **PHILOSOPHER_E**)
- **FORK_E** (shared between **PHILOSOPHER_E** and **PHILOSOPHER_A**)

## Workflow

Each philosopher follows this sequence:

1. Think (call `think`)
2. Eat (call `eat` — requires both adjacent forks to be available; if not available, wait and retry)
3. Finish

## Constraints

- Each fork can be held by at most one philosopher at a time.
- A philosopher must hold both adjacent forks to eat.
- After eating, a philosopher must put down both forks before finishing.
- All philosophers must eventually eat. No philosopher may starve indefinitely.

## Properties (verified by TLC)

- Safety: Each fork held by at most one philosopher at a time.
- Liveness: All philosophers eventually eat and terminate. No deadlock. All forks returned upon completion.
