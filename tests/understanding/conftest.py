import pytest

from tests.source.helpers import Played
from tests.source.helpers import played as simulated


@pytest.fixture(scope="session")
def played() -> Played:
    """Seed 1 on the comeback, simulated once for every test that reads it."""
    return simulated("comeback", 1)
