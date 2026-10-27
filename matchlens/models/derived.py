"""Group B: derived understanding.

Computed from the match record by deterministic code, never by AI: running the detectors again
on the same match gives identical output, which is what lets the verifier recompute a value.
Append-only like group A, so every model is frozen. Recalibrating emits a new row; it never
edits an old one.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from matchlens.models.enums import EpochTrigger, Mechanism, PossessionOutcome, Signal, Trend, Zone
from matchlens.models.match_record import ClockMs

UnitInterval = Annotated[float, Field(ge=0, le=1)]


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Possession(_Record):
    """A sequence of consecutive events by one team.

    Events in stopped play belong to no possession, so an event may be in none of these.
    """

    possession_id: str
    team: str
    start_clock_ms: ClockMs
    end_clock_ms: ClockMs
    pass_count: Annotated[int, Field(ge=0)]
    start_zone: Zone
    end_zone: Zone
    outcome: PossessionOutcome
    event_ids: Annotated[tuple[str, ...], Field(min_length=1)]


class SignalReading(_Record):
    """One observation of a signal for one team. Citable as evidence by `reading_id`."""

    reading_id: str
    signal: Signal
    team: str
    clock_ms: ClockMs
    window_ms: ClockMs  # the effective window, clamped to the epoch start (D15)
    value: float  # in the signal's own units
    baseline: float
    z_match: float  # against this match's baseline: "something changed"
    z_prior: float  # against the offline prior: "this match is unusual"
    trend: Trend
    confidence: UnitInterval
    epoch_id: str


class PositionReading(_Record):
    """One thing the frames showed about how a shot came about (Q48). Citable by `reading_id`.

    Measured by Understanding, the only reader of frames, when the shot arrives, so a claim can
    say what the positions showed while no agent reads a frame (invariant 1). It cites the shot it
    was measured for and the frames it was measured from (invariant 4). `start_ms` and `end_ms`
    are the frames' clocks: one frame for an overload, the first and last of a run.

    - `overload`: `value` attackers and `against` defenders, outfield, near the ball as the final
      pass was played.
    - `decoy_run`: `player`'s run took `opponent` `value` metres with him, away from the shot.
    - `early_run`: `player`, the shooter, covered `value` metres before the pass reached him.
    """

    reading_id: str
    mechanism: Mechanism
    team: str  # the attacking side
    shot_id: str
    clock_ms: ClockMs  # the shot's: when the reading could first be taken
    start_ms: ClockMs
    end_ms: ClockMs
    player: str | None
    opponent: str | None
    value: float
    against: float | None
    frame_seqs: Annotated[tuple[int, ...], Field(min_length=1)]


class Epoch(_Record):
    """A stretch of match with constant game state.

    `score_state` and `player_counts` are keyed by `team_id` and derived from the event log
    (D16). `trigger` is None only for the opening epoch, which starts at kickoff rather than
    at a structural break.
    """

    epoch_id: str
    match_id: str
    start_clock_ms: ClockMs
    score_state: dict[str, Annotated[int, Field(ge=0)]]
    player_counts: dict[str, Annotated[int, Field(ge=0)]]
    trigger: EpochTrigger | None


class ShotValue(_Record):
    """Shot quality for one shot: a hand-calibrated lookup, not a trained model. Never "xG"."""

    event_id: str
    value: UnitInterval
    distance: Annotated[float, Field(ge=0)]  # metres, kept so the number is explainable
    angle: float  # kept so the number is explainable
    model_version: str
