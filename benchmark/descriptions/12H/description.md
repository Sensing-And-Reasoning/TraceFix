# Collaborative Kitchen (Multi-Step with Failures)

Three chefs each prepare their own dish for a three-course meal. Unlike the basic and advanced variants, each dish requires multiple preparation steps using different equipment, and cooking can fail.

## Agents
- **CHEF_A**: prepares the appetizer (needs **PREP_STATION**, **STOVETOP**, and **OVEN**)
- **CHEF_B**: prepares the main course (needs **PREP_STATION**, **STOVETOP**, and **OVEN**)
- **CHEF_C**: prepares the dessert (needs **PREP_STATION** and **OVEN**)

## Shared Resources
- **OVEN**: shared kitchen oven (one chef at a time)
- **STOVETOP**: shared stovetop burners (one chef at a time)
- **PREP_STATION**: shared preparation counter (one chef at a time)

## Workflow

Each dish requires three phases:
1. **Prep phase**: Chef uses the **PREP_STATION** to prepare mise en place (ingredients and base components)
2. **Cook phase**: Chef uses either the **STOVETOP** or the **OVEN** to cook. Cooking CAN FAIL — if cooking fails, the chef must discard the attempt, return to prep (using the **PREP_STATION**), re-prepare, and then re-cook
3. **Plate phase**: Chef uses the **PREP_STATION** again to plate the completed dish with the received ingredient

### CHEF_A
- Preps mise en place at **PREP_STATION**, then cooks appetizer base on **STOVETOP** or in **OVEN** (can fail, requiring re-prep and re-cook)
- Prepares sauce ingredient for **CHEF_C** (requires **STOVETOP**, can fail)
- Receives garnish from **CHEF_B**, then plates the appetizer at **PREP_STATION**

### CHEF_B
- Preps mise en place at **PREP_STATION**, then cooks main course base on **STOVETOP** or in **OVEN** (can fail, requiring re-prep and re-cook)
- Prepares garnish ingredient for **CHEF_A** (requires **STOVETOP**, can fail)
- Receives glaze from **CHEF_C**, then plates the main course at **PREP_STATION**

### CHEF_C
- Preps mise en place at **PREP_STATION**, then cooks dessert base in **OVEN** (can fail, requiring re-prep and re-cook)
- Prepares glaze ingredient for **CHEF_B** (requires **OVEN**, can fail)
- Receives sauce from **CHEF_A**, then plates the dessert at **PREP_STATION**

A dish is only complete when the base dish is cooked successfully AND the plating combines it with the received ingredient.

## Goal
All three dishes are completed: each chef has successfully prepped, cooked, and plated their dish with the received ingredient.
