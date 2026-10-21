"""Shot quality: a 0–1 value per shot from its distance and angle (U2). Never called xG.

A hand-calibrated closed form, not a fitted model. Both inputs stay on the `ShotValue` row, so
every value can be explained from what is stored next to it.

    quality = exp(-distance / DISTANCE_SCALE_M) * (FLOOR + (1 - FLOOR) * cos(angle))

`distance` is metres from the centre of the goal attacked. `angle` is degrees off the goal's
centre line: 0 straight in front, 90 level with the goal line. Both factors only fall as their
input grows, so the value is monotonic in each, and it is clamped to [0, 1]. A penalty is a
fixed constant, not the lookup.
"""

import hashlib
import inspect
import math
from collections.abc import Iterable

from matchlens.models import Action, Event, Match, Outcome, ShotValue, normalise_xy

# Bump by hand whenever a constant below changes; old rows keep the version they were made with.
MODEL_VERSION = "shot-quality-1"

DISTANCE_SCALE_M = 8.0  # value falls by a factor of e every 8 m
FLOOR = 0.05  # what is left of the angle factor level with the goal line
PENALTY_VALUE = 0.76

# A free kick taken straight at goal ends in one of these; one passed short does not.
_AT_GOAL = frozenset({Outcome.SAVED, Outcome.GOAL, Outcome.OFF_TARGET, Outcome.BLOCKED})


def is_shot(event: Event) -> bool:
    """A shot, a penalty, or a free kick struck directly at goal."""
    if event.action in (Action.SHOT, Action.PENALTY):
        return True
    return event.action is Action.FREE_KICK and event.outcome in _AT_GOAL


def quality(distance_m: float, angle_deg: float) -> float:
    """The lookup itself, from the two inputs the row keeps."""
    angle = math.radians(min(max(angle_deg, 0.0), 90.0))
    raw = math.exp(-max(distance_m, 0.0) / DISTANCE_SCALE_M) * (
        FLOOR + (1 - FLOOR) * math.cos(angle)
    )
    return min(max(raw, 0.0), 1.0)


def value(event: Event, match: Match) -> ShotValue:
    """The `ShotValue` of one shot. Raises ValueError for anything that is not a shot."""
    if not is_shot(event):
        raise ValueError(f"{event.event_id} is a {event.action}, not a shot")
    assert event.start_x is not None and event.start_y is not None  # a shot has a position
    team = next(t for t in match.teams if t.team_id == event.team)
    # Seen from the shooter's side, they attack towards +x, so the goal is at (length / 2, 0).
    x, y = normalise_xy(event.start_x, event.start_y, team.attack_direction(event.period))
    along, across = match.pitch_length_m / 2 - x, abs(y)
    distance = math.hypot(along, across)
    angle = math.degrees(math.atan2(across, along)) if distance else 0.0
    shot = PENALTY_VALUE if event.action is Action.PENALTY else quality(distance, angle)
    return ShotValue(
        event_id=event.event_id,
        value=shot,
        distance=distance,
        angle=angle,
        model_version=MODEL_VERSION,
    )


def values(events: Iterable[Event], match: Match) -> list[ShotValue]:
    """One `ShotValue` per shot in `events`, in their order."""
    return [value(e, match) for e in events if is_shot(e)]


def calibration_fingerprint() -> str:
    """A short hash of the lookup and its constants, so a test notices an unversioned change."""
    calibration = repr((inspect.getsource(quality), DISTANCE_SCALE_M, FLOOR, PENALTY_VALUE))
    return hashlib.sha256(calibration.encode()).hexdigest()[:12]
