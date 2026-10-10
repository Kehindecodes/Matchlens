import pytest

from matchlens.source.archetypes import COMEBACK
from matchlens.source.simulator import simulate
from tests.source.helpers import Played, split


@pytest.fixture(scope="session")
def match_1() -> Played:
    return split(list(simulate(1, COMEBACK)))


@pytest.fixture(scope="session")
def match_2() -> Played:
    return split(list(simulate(2, COMEBACK)))
