"""Parameterized kitchen simulation shared by tasks 12E, 12M, and 12H."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._base import ToolResult
from .sim_base import SimContext


@dataclass
class DishConfig:
    """Configuration for one chef's dish."""

    chef_id: str
    dish_name: str
    needs_equipment: list[str]
    receives_ingredient: str
    receives_from: str


@dataclass
class IngredientConfig:
    """Configuration for one ingredient transfer."""

    name: str
    producer: str
    consumer: str
    needs_equipment: list[str] = field(default_factory=list)


class KitchenSim(SimContext):
    """Shared kitchen simulation with configurable equipment requirements.

    Tracks per-chef progress through base preparation, ingredient preparation,
    and final dish combination.  Detects violations such as missing equipment,
    wrong producer, and missing prerequisites.

    Args:
        dishes: Per-chef dish configurations.
        ingredients: Ingredient transfer configurations.
        equipment: List of shared equipment names (each modeled as a mutex).
    """

    def __init__(
        self,
        dishes: list[DishConfig],
        ingredients: list[IngredientConfig],
        equipment: list[str],
    ) -> None:
        super().__init__()

        self._dishes = {d.chef_id: d for d in dishes}
        self._ingredients = {i.name: i for i in ingredients}
        self._equipment = list(equipment)

        # State tracking
        self._base_prepared: dict[str, bool] = {d.chef_id: False for d in dishes}
        self._ingredient_available: dict[str, bool] = {i.name: False for i in ingredients}
        self._dish_completed: dict[str, bool] = {d.chef_id: False for d in dishes}

        # Initialize equipment as resources
        for eq in equipment:
            self.init_resource(eq)

    # -- Tool implementations --

    def acquire_equipment(self, agent_id: str, equipment: str) -> ToolResult:
        """Attempt to exclusively acquire a piece of equipment."""
        violations = []

        if not self.resource_exists(equipment):
            v = self.log_violation(
                agent_id, "acquire_equipment", "unknown_resource",
                f"Equipment '{equipment}' does not exist",
            )
            violations.append(v)
            result = {"equipment": equipment, "status": "error", "reason": "unknown_resource"}
            self.log_event(agent_id, "acquire_equipment", {"equipment": equipment},
                           success=False, result=result, violations=violations)
            return ToolResult(tool_name="acquire_equipment", success=False,
                              data=result, message=f"Unknown equipment: {equipment}")

        acquired = self.try_acquire(equipment, agent_id)
        if acquired:
            result = {"equipment": equipment, "status": "acquired"}
            self.log_event(agent_id, "acquire_equipment", {"equipment": equipment},
                           success=True, result=result)
            return ToolResult(tool_name="acquire_equipment", success=True,
                              data=result, message=f"Acquired {equipment}")
        else:
            holder = self.holder_of(equipment)
            result = {"equipment": equipment, "status": "busy", "held_by": holder}
            self.log_event(agent_id, "acquire_equipment", {"equipment": equipment},
                           success=True, result=result)
            return ToolResult(tool_name="acquire_equipment", success=True,
                              data=result, message=f"{equipment} is busy (held by {holder})")

    def release_equipment(self, agent_id: str, equipment: str) -> ToolResult:
        """Release a piece of equipment."""
        violations = []

        if not self.resource_exists(equipment):
            v = self.log_violation(
                agent_id, "release_equipment", "unknown_resource",
                f"Equipment '{equipment}' does not exist",
            )
            violations.append(v)
            result = {"equipment": equipment, "status": "error", "reason": "unknown_resource"}
            self.log_event(agent_id, "release_equipment", {"equipment": equipment},
                           success=False, result=result, violations=violations)
            return ToolResult(tool_name="release_equipment", success=False,
                              data=result, message=f"Unknown equipment: {equipment}")

        released = self.release(equipment, agent_id)
        if released:
            result = {"equipment": equipment, "status": "released"}
            self.log_event(agent_id, "release_equipment", {"equipment": equipment},
                           success=True, result=result)
            return ToolResult(tool_name="release_equipment", success=True,
                              data=result, message=f"Released {equipment}")
        else:
            holder = self.holder_of(equipment)
            v = self.log_violation(
                agent_id, "release_equipment", "resource_not_held",
                f"{agent_id} cannot release '{equipment}' "
                f"(held by {holder or 'nobody'})",
            )
            violations.append(v)
            result = {"equipment": equipment, "status": "error", "reason": "resource_not_held"}
            self.log_event(agent_id, "release_equipment", {"equipment": equipment},
                           success=False, result=result, violations=violations)
            return ToolResult(tool_name="release_equipment", success=False,
                              data=result, message=f"Cannot release {equipment}: not held by {agent_id}")

    def prepare_base_dish(self, agent_id: str, dish: str) -> ToolResult:
        """Prepare the base component of a dish using kitchen equipment."""
        violations = []
        dish_cfg = self._dishes.get(agent_id)

        if dish_cfg is None:
            v = self.log_violation(
                agent_id, "prepare_base_dish", "wrong_producer",
                f"{agent_id} is not assigned to any dish",
            )
            violations.append(v)
            result = {"dish": dish, "status": "error", "reason": "wrong_producer"}
            self.log_event(agent_id, "prepare_base_dish", {"dish": dish},
                           success=False, result=result, violations=violations)
            return ToolResult(tool_name="prepare_base_dish", success=False,
                              data=result, message=f"{agent_id} is not assigned to any dish")

        self._base_prepared[agent_id] = True
        result = {"dish": dish, "status": "base dish prepared"}
        self.log_event(agent_id, "prepare_base_dish", {"dish": dish},
                       success=True, result=result)
        return ToolResult(tool_name="prepare_base_dish", success=True,
                          data=result, message=f"Base dish prepared: {dish}")

    def prepare_ingredient(self, agent_id: str, ingredient: str, for_chef: str) -> ToolResult:
        """Prepare an ingredient for another chef's dish."""
        violations = []
        ing_cfg = self._ingredients.get(ingredient)

        if ing_cfg is None:
            v = self.log_violation(
                agent_id, "prepare_ingredient", "unknown_resource",
                f"Unknown ingredient: '{ingredient}'",
            )
            violations.append(v)
            result = {"ingredient": ingredient, "status": "error", "reason": "unknown_resource"}
            self.log_event(agent_id, "prepare_ingredient",
                           {"ingredient": ingredient, "for_chef": for_chef},
                           success=False, result=result, violations=violations)
            return ToolResult(tool_name="prepare_ingredient", success=False,
                              data=result, message=f"Unknown ingredient: {ingredient}")

        # Check producer authorization
        if ing_cfg.producer != agent_id:
            v = self.log_violation(
                agent_id, "prepare_ingredient", "wrong_producer",
                f"{agent_id} cannot prepare '{ingredient}' "
                f"(assigned to {ing_cfg.producer})",
            )
            violations.append(v)
            result = {"ingredient": ingredient, "status": "error", "reason": "wrong_producer"}
            self.log_event(agent_id, "prepare_ingredient",
                           {"ingredient": ingredient, "for_chef": for_chef},
                           success=False, result=result, violations=violations)
            return ToolResult(tool_name="prepare_ingredient", success=False,
                              data=result, message=f"Wrong producer: {ingredient} is {ing_cfg.producer}'s job")

        self._ingredient_available[ingredient] = True
        result = {"ingredient": ingredient, "for_chef": for_chef, "status": "ingredient prepared"}
        self.log_event(agent_id, "prepare_ingredient",
                       {"ingredient": ingredient, "for_chef": for_chef},
                       success=True, result=result)
        return ToolResult(tool_name="prepare_ingredient", success=True,
                          data=result, message=f"Ingredient prepared: {ingredient}")

    def combine_dish(self, agent_id: str, dish: str, ingredient: str) -> ToolResult:
        """Combine base dish with ingredient to complete the final dish."""
        violations = []
        dish_cfg = self._dishes.get(agent_id)

        if dish_cfg is None:
            v = self.log_violation(
                agent_id, "combine_dish", "wrong_producer",
                f"{agent_id} is not assigned to any dish",
            )
            violations.append(v)
            result = {"dish": dish, "ingredient": ingredient, "status": "error",
                      "reason": "wrong_producer"}
            self.log_event(agent_id, "combine_dish",
                           {"dish": dish, "ingredient": ingredient},
                           success=False, result=result, violations=violations)
            return ToolResult(tool_name="combine_dish", success=False,
                              data=result, message=f"{agent_id} is not assigned to any dish")

        # Check base dish prepared
        if not self._base_prepared.get(agent_id, False):
            v = self.log_violation(
                agent_id, "combine_dish", "missing_prerequisite",
                f"{agent_id} has not prepared base dish yet",
            )
            violations.append(v)

        # Check ingredient available
        expected_ingredient = dish_cfg.receives_ingredient
        if not self._ingredient_available.get(expected_ingredient, False):
            v = self.log_violation(
                agent_id, "combine_dish", "missing_prerequisite",
                f"Ingredient '{expected_ingredient}' is not available yet",
            )
            violations.append(v)

        if violations:
            result = {"dish": dish, "ingredient": ingredient, "status": "error",
                      "reason": "missing_prerequisite"}
            self.log_event(agent_id, "combine_dish",
                           {"dish": dish, "ingredient": ingredient},
                           success=False, result=result, violations=violations)
            return ToolResult(tool_name="combine_dish", success=False,
                              data=result, message=f"Missing prerequisites for combining {dish}")

        self._dish_completed[agent_id] = True
        result = {"dish": dish, "ingredient": ingredient, "status": "dish completed"}
        self.log_event(agent_id, "combine_dish",
                       {"dish": dish, "ingredient": ingredient},
                       success=True, result=result)
        return ToolResult(tool_name="combine_dish", success=True,
                          data=result, message=f"Dish completed: {dish}")

    def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
        """Return resource IDs needed by *tool_name*.

        Extends the metadata-driven base to also handle ``prepare_ingredient``
        dynamically: the equipment required depends on which ingredient is
        being prepared (stored in ``IngredientConfig.needs_equipment``).
        """
        if tool_name == "prepare_ingredient":
            ingredient = kwargs.get("ingredient", "")
            ing_cfg = self._ingredients.get(ingredient)
            if ing_cfg and ing_cfg.needs_equipment:
                return list(ing_cfg.needs_equipment)
            return []
        return super().resource_requirements(tool_name, **kwargs)

    # -- SimContext interface --

    def make_tools(self) -> dict[str, Any]:
        """Return tool dispatch dict for sim-mode registry."""
        return {
            "prepare_base_dish": self.prepare_base_dish,
            "prepare_ingredient": self.prepare_ingredient,
            "combine_dish": self.combine_dish,
        }

    def is_complete(self) -> bool:
        """All dishes must be completed."""
        return all(self._dish_completed.values())

    @property
    def progress(self) -> dict[str, Any]:
        """Current progress toward the goal."""
        return {
            "base_prepared": dict(self._base_prepared),
            "ingredient_available": dict(self._ingredient_available),
            "dish_completed": dict(self._dish_completed),
            "all_complete": self.is_complete(),
        }
