import pytest

from matchlens.source import simulate
from tests.source.helpers import Played, split


@pytest.fixture(scope="session")
def played() -> Played:
    """Seed 1, simulated once for every understanding test."""
    return split(list(simulate(1)))
