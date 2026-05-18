"""Dining philosophers simulation config for task 9M."""

from benchmark.tools.sim_philosophers import PhilosophersSim

_PHILOSOPHER_IDS = [
    "PHILOSOPHER_A",
    "PHILOSOPHER_B",
    "PHILOSOPHER_C",
    "PHILOSOPHER_D",
    "PHILOSOPHER_E",
]

_FORKS = {
    "PHILOSOPHER_A": ("FORK_A", "FORK_E"),
    "PHILOSOPHER_B": ("FORK_B", "FORK_A"),
    "PHILOSOPHER_C": ("FORK_C", "FORK_B"),
    "PHILOSOPHER_D": ("FORK_D", "FORK_C"),
    "PHILOSOPHER_E": ("FORK_E", "FORK_D"),
}


class FivePhilosophersSim(PhilosophersSim):
    """9M: Five dining philosophers with five shared forks."""

    def __init__(self) -> None:
        super().__init__(
            philosopher_ids=_PHILOSOPHER_IDS,
            forks=_FORKS,
        )
