"""Dining philosophers simulation config for task 9E."""

from benchmark.tools.sim_philosophers import PhilosophersSim

_PHILOSOPHER_IDS = ["PHILOSOPHER_A", "PHILOSOPHER_B", "PHILOSOPHER_C"]

_FORKS = {
    "PHILOSOPHER_A": ("FORK_A", "FORK_C"),
    "PHILOSOPHER_B": ("FORK_B", "FORK_A"),
    "PHILOSOPHER_C": ("FORK_C", "FORK_B"),
}


class ThreePhilosophersSim(PhilosophersSim):
    """9E: Three dining philosophers with three shared forks."""

    def __init__(self) -> None:
        super().__init__(
            philosopher_ids=_PHILOSOPHER_IDS,
            forks=_FORKS,
        )
