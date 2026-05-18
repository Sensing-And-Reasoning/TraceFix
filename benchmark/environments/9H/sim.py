"""Dining philosophers simulation config for task 9H."""

from benchmark.tools.sim_philosophers import PhilosophersSim

_PHILOSOPHER_IDS = [
    "PHILOSOPHER_A",
    "PHILOSOPHER_B",
    "PHILOSOPHER_C",
    "PHILOSOPHER_D",
    "PHILOSOPHER_E",
    "PHILOSOPHER_F",
    "PHILOSOPHER_G",
]

_FORKS = {
    "PHILOSOPHER_A": ("FORK_A", "FORK_G"),
    "PHILOSOPHER_B": ("FORK_B", "FORK_A"),
    "PHILOSOPHER_C": ("FORK_C", "FORK_B"),
    "PHILOSOPHER_D": ("FORK_D", "FORK_C"),
    "PHILOSOPHER_E": ("FORK_E", "FORK_D"),
    "PHILOSOPHER_F": ("FORK_F", "FORK_E"),
    "PHILOSOPHER_G": ("FORK_G", "FORK_F"),
}


class SevenPhilosophersSim(PhilosophersSim):
    """9H: Seven dining philosophers with seven shared forks."""

    def __init__(self) -> None:
        super().__init__(
            philosopher_ids=_PHILOSOPHER_IDS,
            forks=_FORKS,
        )
