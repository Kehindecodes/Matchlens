"""Serves lens configuration as data"""

import json
from pathlib import Path

from matchlens import calltrace
from matchlens.models import Lens

LENSES_PATH = Path(__file__).with_name("lenses.json")


def load(path: Path = LENSES_PATH) -> list[Lens]:
    """The lens rows in this file, each validated as a `Lens`."""
    return [Lens.model_validate(row) for row in json.loads(path.read_text())["lenses"]]


_LENSES: tuple[Lens, ...] = tuple(load())


def get(lens_id: str) -> Lens:
    """The lens with this id."""
    calltrace.entered("Lens Registry")
    for lens in _LENSES:
        if lens.lens_id == lens_id:
            return lens
    raise KeyError(lens_id)


def all_lenses() -> list[Lens]:
    """Every active lens."""
    calltrace.entered("Lens Registry")
    return list(_LENSES)
