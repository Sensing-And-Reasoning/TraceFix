"""Kitchen Advanced simulation config for task 12M.

Ingredient preparation REQUIRES equipment — additional coordination needed.
"""

import json
from pathlib import Path

from benchmark.tools.sim_kitchen import DishConfig, IngredientConfig, KitchenSim

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "12M" / "metadata.json").read_text()
)

_EQUIPMENT = ["OVEN", "STOVETOP"]

_DISHES = [
    DishConfig(
        chef_id="CHEF_A",
        dish_name="appetizer",
        needs_equipment=["STOVETOP", "OVEN"],
        receives_ingredient="garnish",
        receives_from="CHEF_B",
    ),
    DishConfig(
        chef_id="CHEF_B",
        dish_name="main_course",
        needs_equipment=["STOVETOP", "OVEN"],
        receives_ingredient="glaze",
        receives_from="CHEF_C",
    ),
    DishConfig(
        chef_id="CHEF_C",
        dish_name="dessert",
        needs_equipment=["OVEN"],
        receives_ingredient="sauce",
        receives_from="CHEF_A",
    ),
]

_INGREDIENTS = [
    IngredientConfig(name="sauce", producer="CHEF_A", consumer="CHEF_C", needs_equipment=["STOVETOP"]),
    IngredientConfig(name="garnish", producer="CHEF_B", consumer="CHEF_A", needs_equipment=["STOVETOP"]),
    IngredientConfig(name="glaze", producer="CHEF_C", consumer="CHEF_B", needs_equipment=["OVEN"]),
]


class KitchenAdvancedSim(KitchenSim):
    """12M: ingredient prep requires equipment."""

    def __init__(self) -> None:
        super().__init__(dishes=_DISHES, ingredients=_INGREDIENTS, equipment=_EQUIPMENT)
        self.load_from_metadata(_METADATA)
