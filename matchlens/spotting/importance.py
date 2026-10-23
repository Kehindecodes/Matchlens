"""How much a moment matters: one formula, with every number in `settings` (M1b).

    importance = type weight * magnitude * confidence

`magnitude` is 0–1 and says how far from ordinary the thing is, in a unit that does not depend on
which signal it came from: a shift's z-scores saturate at `importance_z_saturation`, a chance is
its shot quality, a goal is full. `confidence` is the reading's, and 1 for an event. So a 3σ
territory shift and a 3σ pressing shift score the same at the same confidence.
"""

from matchlens.config import settings
from matchlens.models import MomentType, SignalReading

_WEIGHTS = {
    MomentType.GOAL: settings.importance_goal,
    MomentType.CHANCE: settings.importance_chance,
    MomentType.TACTICAL_SHIFT: settings.importance_tactical_shift,
}


def importance(type_: MomentType, magnitude: float, confidence: float = 1.0) -> float:
    return _WEIGHTS[type_] * magnitude * confidence


def shift_magnitude(reading: SignalReading) -> float:
    """How big a shift is: mostly how far it moved this match's baseline, partly how unusual."""
    saturation = settings.importance_z_saturation
    changed = min(abs(reading.z_match) / saturation, 1.0)
    unusual = min(abs(reading.z_prior) / saturation, 1.0)
    prior_weight = settings.importance_prior_weight
    return (1 - prior_weight) * changed + prior_weight * unusual
