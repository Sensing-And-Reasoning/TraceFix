"""Kitchen Basic simulation config for task 12E.

Ingredient preparation does NOT require equipment — only base dish prep does.
"""

import json
from pathlib import Path

from benchmark.tools.sim_kitchen import DishConfig, IngredientConfig, KitchenSim

_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "12E" / "metadata.json").read_text()
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
    IngredientConfig(name="sauce", producer="CHEF_A", consumer="CHEF_C", needs_equipment=[]),
    IngredientConfig(name="garnish", producer="CHEF_B", consumer="CHEF_A", needs_equipment=[]),
    IngredientConfig(name="glaze", producer="CHEF_C", consumer="CHEF_B", needs_equipment=[]),
]


class KitchenBasicSim(KitchenSim):
    """12E: ingredient prep needs no equipment."""

    def __init__(self) -> None:
        super().__init__(dishes=_DISHES, ingredients=_INGREDIENTS, equipment=_EQUIPMENT)
        self.load_from_metadata(_METADATA)
