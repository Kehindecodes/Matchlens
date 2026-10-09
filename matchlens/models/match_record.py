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
    """One squad member: identity only, loaded pre-match and never touched again (D16).

    There is deliberately no on/off clock. Who was on the pitch at a given clock is derived from
    `is_starter` plus the `substitution` and `red_card` events in the log, so it is reproducible.
    """

    player_id: str
    team_id: str
    shirt: int
    name: str
    position: str
    is_starter: bool  # whether they started the match


class Match(_Record):
    """The root record. Holds exactly two teams: every signal is per-team.

    Period boundaries are not stored: added time is unknown at kickoff, so they are derived from
    the `period_start` / `period_end` events (D16).
    """

    match_id: str
    pitch_length_m: Annotated[float, Field(gt=0)]
    pitch_width_m: Annotated[float, Field(gt=0)]
    kickoff_at: AwareDatetime  # notional start time
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


MATCH_EVENTS = frozenset(
    {
        Action.SUBSTITUTION,
        Action.RED_CARD,
        Action.YELLOW_CARD,
        Action.PERIOD_START,
        Action.PERIOD_END,
    }
)
_NO_ACTOR = frozenset({Action.PERIOD_START, Action.PERIOD_END})


class Event(_Record):
    """One entry in the match log: an on-ball action, or a match event (D16).

    Every on-ball action is recorded, not just the interesting ones. Match events are
    `substitution`, `red_card`, `yellow_card`, `period_start` and `period_end`; they change the
    roster or the clock, and their positional fields, `outcome`, `under_pressure`, `receiver` and
    `body_part` are null.

    `player` is the actor. For a substitution it is the player coming *off*, and `player_on` is
    the one coming on (null for a replacement-less injury). `player` and `team` are null only for
    the period events. `player_on` is null for every other action.

    `frame_ref` is the `seq` of the Frame this event aligns to. It is mandatory, so positional
    context is always recoverable. `receiver` is set for passes; `body_part` for actions where
    it applies (it feeds shot quality).
    """

    event_id: str
    seq: Annotated[int, Field(ge=0)]
    clock_ms: ClockMs
    period: Annotated[int, Field(ge=1)]
    action: Action
    player: str | None
    team: str | None
    start_x: float | None
    start_y: float | None
    end_x: float | None  # for a shot, where it arrived
    end_y: float | None
    outcome: Outcome | None
    receiver: str | None
    player_on: str | None  # substitutions only
    under_pressure: bool | None  # generator-set
    body_part: BodyPart | None
    frame_ref: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _shape_matches_the_action(self):
        if self.action in MATCH_EVENTS:
            unexpected = [
                name
                for name in (
                    "start_x",
                    "start_y",
                    "end_x",
                    "end_y",
                    "outcome",
                    "receiver",
                    "under_pressure",
                    "body_part",
                )  # fmt: skip
                if getattr(self, name) is not None
            ]
            if unexpected:
                raise ValueError(f"{self.action} must not set {', '.join(unexpected)}")
            if self.action in _NO_ACTOR:
                if self.player is not None or self.team is not None:
                    raise ValueError(f"{self.action} has no player or team")
            elif self.player is None or self.team is None:
                raise ValueError(f"{self.action} needs a player and a team")
            if self.player_on is not None and self.action is not Action.SUBSTITUTION:
                raise ValueError("player_on is set only for a substitution")
        else:
            missing = [
                name
                for name in (
                    "player",
                    "team",
                    "start_x",
                    "start_y",
                    "end_x",
                    "end_y",
                    "outcome",
                    "under_pressure",
                )  # fmt: skip
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"{self.action} needs {', '.join(missing)}")
            if self.player_on is not None:
                raise ValueError("player_on is set only for a substitution")
        return self


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
    if event.start_x is None:  # a match event has no position to normalise
        return event.model_copy()
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
