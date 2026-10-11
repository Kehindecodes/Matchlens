"""Serves lens configuration as data"""

from matchlens.models import Lens


def get(lens_id: str) -> Lens:
    """The lens with this id. Stub: the registry is empty until L1."""
    raise KeyError(lens_id)


def all_lenses() -> list[Lens]:
    """Every active lens. Stub: the registry is empty until L1."""
    return []
