# Collaborative Kitchen (Basic)

Three chefs each prepare their own dish for a three-course meal.

## Agents
- **CHEF_A**: prepares the appetizer (needs **STOVETOP** and **OVEN**)
- **CHEF_B**: prepares the main course (needs **STOVETOP** and **OVEN**)
- **CHEF_C**: prepares the dessert (needs **OVEN**)

## Shared Resources
- **OVEN**: shared kitchen oven (one chef at a time)
- **STOVETOP**: shared stovetop burners (one chef at a time)

## Workflow

### CHEF_A
- Prepares the base appetizer dish (requires **STOVETOP** and **OVEN**)
- Prepares sauce ingredient for **CHEF_C** (no equipment needed)
- Receives garnish from **CHEF_B**, then combines with base dish to complete the appetizer

### CHEF_B
- Prepares the base main course dish (requires **STOVETOP** and **OVEN**)
- Prepares garnish ingredient for **CHEF_A** (no equipment needed)
- Receives glaze from **CHEF_C**, then combines with base dish to complete the main course

### CHEF_C
- Prepares the base dessert dish (requires **OVEN**)
- Prepares glaze ingredient for **CHEF_B** (no equipment needed)
- Receives sauce from **CHEF_A**, then combines with base dish to complete the dessert

Each chef can prepare their ingredient for another chef at any time without equipment. A dish is only complete when both components are combined.

## Goal
All three dishes are completed.
