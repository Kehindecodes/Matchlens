"""Group A: the match record.

A faithful record of what happened, with no view on what mattered. Append-only: every model is
frozen, because nothing here is edited after emission.

Conventions that hold across the module:

- `clock_ms` is an int count of milliseconds from kickoff. Not seconds, not a timedelta, not
  wall clock.
- `seq` is the ordering key for the whole system. It is monotonic across frames *and* events, so
  an event and the frame it aligns to can be ordered against each other.
- Coordinates are metres, origin at the centre spot, x along the length. They are stored raw.
  Attack direction is applied at read time through the `normalise_*` helpers, which return new
  objects and never touch the stored values.
"""

from typing import Annotated, Literal, NamedTuple

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from matchlens.models.enums import Action, BodyPart, Outcome, Phase

ClockMs = Annotated[int, Field(ge=0)]
AttackDirection = Literal[1, -1]  # +1 attacks towards +x, -1 towards -x


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PeriodBoundary(_Record):
    """Where one period starts and ends on the match clock, added time included."""

    period: Annotated[int, Field(ge=1)]
    start_clock_ms: ClockMs
    end_clock_ms: ClockMs

    @model_validator(mode="after")
    def _ends_after_it_starts(self):
        if self.end_clock_ms <= self.start_clock_ms:
            raise ValueError(f"period {self.period} must end after it starts")
        return self


class Team(_Record):
    team_id: str
    match_id: str
    name: str
    short_name: str
    formation: str
    is_home: bool
    attack_direction_by_period: dict[int, AttackDirection]

    def attack_direction(self, period: int) -> AttackDirection:
        """Which way this team attacks in `period`. Raises KeyError for an unknown period."""
        return self.attack_direction_by_period[period]


class Player(_Record):
    """One squad member.

    `on_clock_ms` / `off_clock_ms` are what the verifier's entity check reads. A null
    `off_clock_ms` means the player finished the match. A null `on_clock_ms` means an unused
    substitute who never entered.
    """

    player_id: str
    team_id: str
    shirt: int
    name: str
    position: str
    is_starter: bool
    on_clock_ms: ClockMs | None
    off_clock_ms: ClockMs | None

    @model_validator(mode="after")
    def _consistent_pitch_time(self):
        if self.is_starter and self.on_clock_ms != 0:
            raise ValueError("a starter enters at kickoff, so on_clock_ms must be 0")
        if self.off_clock_ms is not None:
            if self.on_clock_ms is None:
                raise ValueError("a player who never entered cannot have left")
            if self.off_clock_ms <= self.on_clock_ms:
                raise ValueError("off_clock_ms must be after on_clock_ms")
        return self


def was_on_pitch(player: Player, clock_ms: int) -> bool:
    """Whether `player` was on the pitch at `clock_ms`.

    The interval is inclusive at the start and exclusive at the end: `on_clock_ms <= clock_ms <
    off_clock_ms`. A claim at exactly `on_clock_ms` is valid; a claim at exactly `off_clock_ms`
    is not. A null `off_clock_ms` has no upper bound, and a null `on_clock_ms` (unused
    substitute) is never on the pitch.
    """
    if player.on_clock_ms is None or clock_ms < player.on_clock_ms:
        return False
    return player.off_clock_ms is None or clock_ms < player.off_clock_ms


class Match(_Record):
    """The root record. Holds exactly two teams: every signal is per-team."""

    match_id: str
    pitch_length_m: Annotated[float, Field(gt=0)]
    pitch_width_m: Annotated[float, Field(gt=0)]
    kickoff_at: AwareDatetime  # notional start time
    period_boundaries: Annotated[tuple[PeriodBoundary, ...], Field(min_length=1)]
    archetype_id: str
    seed: int  # regenerates a byte-identical match
    teams: tuple[Team, Team]

    @model_validator(mode="after")
    def _teams_are_a_home_and_away_pair(self):
        if len({t.team_id for t in self.teams}) != 2:
            raise ValueError("the two teams must have distinct team_ids")
        if sum(t.is_home for t in self.teams) != 1:
            raise ValueError("exactly one team must be the home team")
        if any(t.match_id != self.match_id for t in self.teams):
            raise ValueError("every team must belong to this match")
        return self

    @model_validator(mode="after")
    def _periods_are_ordered_and_do_not_overlap(self):
        for prev, nxt in zip(self.period_boundaries, self.period_boundaries[1:], strict=False):
            if nxt.period <= prev.period or nxt.start_clock_ms < prev.end_clock_ms:
                raise ValueError("period boundaries must be ordered and non-overlapping")
        return self


class PlayerPosition(NamedTuple):
    """One player in a frame. Serialises as the array `[player_id, x, y, speed]`."""

    player_id: str
    x: float
    y: float
    speed: float


class Frame(_Record):
    """A positional snapshot of everyone on the pitch. Memory only, never a row per frame.

    `players` is positional rather than a list of objects: at thousands of frames per match the
    key names would roughly double the payload. Its length is not fixed at 22; it shrinks after
    a sending-off.
    """

    seq: Annotated[int, Field(ge=0)]
    clock_ms: ClockMs
    period: Annotated[int, Field(ge=1)]
    phase: Phase
    ball_x: float
    ball_y: float
    ball_z: float  # height
    ball_speed: Annotated[float, Field(ge=0)]  # m/s
    carrier: str | None  # null if the ball is loose or in flight
    players: tuple[PlayerPosition, ...]

    @model_validator(mode="after")
    def _carrier_is_on_the_frame(self):
        ids = [p.player_id for p in self.players]
        if len(set(ids)) != len(ids):
            raise ValueError("a player appears twice in one frame")
        if self.carrier is not None and self.carrier not in ids:
            raise ValueError("the carrier must be one of the players in the frame")
        return self


class Event(_Record):
    """One on-ball action. Every action is recorded, not just the interesting ones.

    `frame_ref` is the `seq` of the Frame this event aligns to. It is mandatory, so positional
    context is always recoverable. `receiver` is set for passes; `body_part` for actions where
    it applies (it feeds shot quality).
    """

    event_id: str
    seq: Annotated[int, Field(ge=0)]
    clock_ms: ClockMs
    period: Annotated[int, Field(ge=1)]
    action: Action
    player: str
    team: str
    start_x: float
    start_y: float
    end_x: float  # for a shot, where it arrived
    end_y: float
    outcome: Outcome
    receiver: str | None
    under_pressure: bool  # generator-set
    body_part: BodyPart | None
    frame_ref: Annotated[int, Field(ge=0)]


# --- read-time coordinate normalisation ----------------------------------------------------------
# Pure: each returns a new value and leaves its input untouched.


def normalise_xy(x: float, y: float, direction: AttackDirection) -> tuple[float, float]:
    """Express a point so the team attacks towards +x.

    A team attacking -x is rotated 180 degrees about the centre spot, which flips both axes and
    keeps the pitch's handedness.
    """
    return (x, y) if direction == 1 else (-x, -y)


def normalise_event(event: Event, team: Team) -> Event:
    """`event` seen from `team`'s perspective in the event's period."""
    d = team.attack_direction(event.period)
    sx, sy = normalise_xy(event.start_x, event.start_y, d)
    ex, ey = normalise_xy(event.end_x, event.end_y, d)
    return event.model_copy(update={"start_x": sx, "start_y": sy, "end_x": ex, "end_y": ey})


def normalise_frame(frame: Frame, team: Team) -> Frame:
    """`frame` seen from `team`'s perspective in the frame's period."""
    d = team.attack_direction(frame.period)
    bx, by = normalise_xy(frame.ball_x, frame.ball_y, d)
    players = tuple(
        PlayerPosition(p.player_id, *normalise_xy(p.x, p.y, d), p.speed) for p in frame.players
    )
    return frame.model_copy(update={"ball_x": bx, "ball_y": by, "players": players})
