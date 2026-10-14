"""Serves lens configuration as data"""

from matchlens import calltrace
from matchlens.models import ClaimType, Depth, DetailLevel, Lens, MomentType, Scope

# Stub until L1: one row, the default lens. L1 replaces this with the three presets as config rows.
_LENSES: tuple[Lens, ...] = (
    Lens(
        lens_id="match_casual",
        name="Whole match",
        audience="casual viewers",
        scope=Scope.MATCH,
        breakthrough_types=(MomentType.GOAL,),
        depth=Depth.CASUAL,
        importance_threshold=0.0,
        max_cards_per_10min=3,
        allowed_claim_types=tuple(ClaimType),
        detail_level=DetailLevel.MINIMAL,
        language="en",
        focus_team=None,
        focus_player=None,
    ),
)


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
