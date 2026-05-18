"""Kitchen Multi-Step with Failures simulation config for task 12H.

Three chefs share oven + stovetop + prep_station.  Multi-step dish
preparation with cooking failures that force re-prep + re-cook cycles.

Deadlock traps:
  1. 3-lock contention — all three chefs need prep_station, stovetop/oven
  2. Hold-and-wait on failure — chef holds stovetop, needs prep_station
     for re-prep after cook failure
  3. Circular ingredient deps — A→C, B→A, C→B with equipment for all
"""

import json
from pathlib import Path
from typing import Any

from benchmark.tools._base import ToolResult
from benchmark.tools.sim_kitchen import DishConfig, IngredientConfig, KitchenSim

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "12H" / "metadata.json").read_text()
)

_EQUIPMENT = ["OVEN", "STOVETOP", "PREP_STATION"]

_DISHES = [
    DishConfig(
        chef_id="CHEF_A",
        dish_name="appetizer",
        needs_equipment=["PREP_STATION", "STOVETOP", "OVEN"],
        receives_ingredient="garnish",
        receives_from="CHEF_B",
    ),
    DishConfig(
        chef_id="CHEF_B",
        dish_name="main_course",
        needs_equipment=["PREP_STATION", "STOVETOP", "OVEN"],
        receives_ingredient="glaze",
        receives_from="CHEF_C",
    ),
    DishConfig(
        chef_id="CHEF_C",
        dish_name="dessert",
        needs_equipment=["PREP_STATION", "OVEN"],
        receives_ingredient="sauce",
        receives_from="CHEF_A",
    ),
]

_INGREDIENTS = [
    IngredientConfig(name="sauce", producer="CHEF_A", consumer="CHEF_C", needs_equipment=["STOVETOP"]),
    IngredientConfig(name="garnish", producer="CHEF_B", consumer="CHEF_A", needs_equipment=["STOVETOP"]),
    IngredientConfig(name="glaze", producer="CHEF_C", consumer="CHEF_B", needs_equipment=["OVEN"]),
]


class KitchenMultiStepSim(KitchenSim):
    """12H: Multi-step dish prep with cooking failures and 3-lock contention.

    12H uses finer-grained tools than 12E/12M:
      prep_mise_en_place → cook_on_stovetop/cook_in_oven → plate_dish
    instead of the base kitchen's:
      prepare_base_dish → combine_dish
    """

    _DECISION_TOOLS: dict[str, float] = {
        "cook_on_stovetop": 0.3,
        "cook_in_oven": 0.3,
        "prepare_ingredient": 0.3,
    }

    def __init__(self) -> None:
        super().__init__(dishes=_DISHES, ingredients=_INGREDIENTS, equipment=_EQUIPMENT)
        self.load_from_metadata(_METADATA)
        self._cooked: dict[str, bool] = {d.chef_id: False for d in _DISHES}

    # -- 12H-specific tool methods --

    def prepare_ingredient(self, agent_id: str, ingredient: str = "",
                           for_chef: str = "", **kwargs: Any) -> ToolResult:
        """Prepare an ingredient for another chef. Requires equipment (STOVETOP or OVEN, ingredient-dependent). Can fail — requires re-preparation."""
        if self.should_fail("prepare_ingredient", agent_id):
            result = {"ingredient": ingredient, "for_chef": for_chef,
                      "status": "preparation_failed", "chef": agent_id}
            self.log_event(agent_id, "prepare_ingredient",
                           {"ingredient": ingredient, "for_chef": for_chef},
                           success=False, result=result)
            return ToolResult(tool_name="prepare_ingredient", success=False,
                              data=result,
                              message=f"Ingredient preparation failed: {ingredient}")
        return super().prepare_ingredient(
            agent_id, ingredient=ingredient, for_chef=for_chef
        )

    def prep_mise_en_place(self, agent_id: str, dish: str = "", **kwargs: Any) -> ToolResult:
        """Prepare ingredients and base components at the prep station. Requires holding the PREP_STATION."""
        self._base_prepared[agent_id] = True
        result = {"dish": dish, "status": "mise en place done", "chef": agent_id}
        self.log_event(agent_id, "prep_mise_en_place", {"dish": dish},
                       success=True, result=result)
        return ToolResult(tool_name="prep_mise_en_place", success=True,
                          data=result, message=f"Mise en place done: {dish}")

    def cook_on_stovetop(self, agent_id: str, item: str = "", **kwargs: Any) -> ToolResult:
        """Cook on stovetop. Requires holding the STOVETOP. Can fail — requires re-prep on failure."""
        if self.should_fail("cook_on_stovetop", agent_id):
            # Failure resets prep so chef must re-prep
            self._base_prepared[agent_id] = False
            result = {"item": item, "status": "cook_failed", "chef": agent_id}
            self.log_event(agent_id, "cook_on_stovetop", {"item": item},
                           success=False, result=result)
            return ToolResult(tool_name="cook_on_stovetop", success=False,
                              data=result, message=f"Stovetop cook failed: {item}")

        self._cooked[agent_id] = True
        result = {"item": item, "status": "cooked on stovetop", "chef": agent_id}
        self.log_event(agent_id, "cook_on_stovetop", {"item": item},
                       success=True, result=result)
        return ToolResult(tool_name="cook_on_stovetop", success=True,
                          data=result, message=f"Cooked on stovetop: {item}")

    def cook_in_oven(self, agent_id: str, item: str = "", **kwargs: Any) -> ToolResult:
        """Cook in oven. Requires holding the OVEN. Can fail — requires re-prep on failure."""
        if self.should_fail("cook_in_oven", agent_id):
            self._base_prepared[agent_id] = False
            result = {"item": item, "status": "cook_failed", "chef": agent_id}
            self.log_event(agent_id, "cook_in_oven", {"item": item},
                           success=False, result=result)
            return ToolResult(tool_name="cook_in_oven", success=False,
                              data=result, message=f"Oven cook failed: {item}")

        self._cooked[agent_id] = True
        result = {"item": item, "status": "cooked in oven", "chef": agent_id}
        self.log_event(agent_id, "cook_in_oven", {"item": item},
                       success=True, result=result)
        return ToolResult(tool_name="cook_in_oven", success=True,
                          data=result, message=f"Cooked in oven: {item}")

    def plate_dish(self, agent_id: str, dish: str = "",
                   ingredient: str = "", **kwargs: Any) -> ToolResult:
        """Plate the completed dish with received ingredient. Requires holding the PREP_STATION."""
        violations = []

        if not self._base_prepared.get(agent_id, False):
            v = self.log_violation(agent_id, "plate_dish", "missing_prerequisite",
                                   f"{agent_id} has not prepped yet")
            violations.append(v)

        if not self._cooked.get(agent_id, False):
            v = self.log_violation(agent_id, "plate_dish", "missing_prerequisite",
                                   f"{agent_id} has not cooked successfully yet")
            violations.append(v)

        dish_cfg = self._dishes.get(agent_id)
        if dish_cfg:
            expected = dish_cfg.receives_ingredient
            if not self._ingredient_available.get(expected, False):
                v = self.log_violation(agent_id, "plate_dish", "missing_prerequisite",
                                       f"Ingredient '{expected}' not available yet")
                violations.append(v)

        if violations:
            result = {"dish": dish, "ingredient": ingredient, "status": "error",
                      "reason": "missing_prerequisite"}
            self.log_event(agent_id, "plate_dish",
                           {"dish": dish, "ingredient": ingredient},
                           success=False, result=result, violations=violations)
            return ToolResult(tool_name="plate_dish", success=False,
                              data=result, message=f"Missing prerequisites for plating {dish}")

        self._dish_completed[agent_id] = True
        result = {"dish": dish, "ingredient": ingredient, "status": "dish plated"}
        self.log_event(agent_id, "plate_dish",
                       {"dish": dish, "ingredient": ingredient},
                       success=True, result=result)
        return ToolResult(tool_name="plate_dish", success=True,
                          data=result, message=f"Dish plated: {dish}")

    # -- Overrides --

    def make_tools(self) -> dict[str, Any]:
        return {
            "prep_mise_en_place": self.prep_mise_en_place,
            "cook_on_stovetop": self.cook_on_stovetop,
            "cook_in_oven": self.cook_in_oven,
            "plate_dish": self.plate_dish,
            "prepare_ingredient": self.prepare_ingredient,
        }

    @property
    def progress(self) -> dict[str, Any]:
        base = super().progress
        base["cooked"] = dict(self._cooked)
        return base
