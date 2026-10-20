"""Possessions: the event log cut into consecutive on-ball sequences by one team (U1).

A possession starts on the event that gains control, a restart included (Q10), and holds that
team's on-ball events. It ends on a shot, on the ball going out, on a foul, on the half ending,
or when the other team's next on-ball event takes control. A foul is the last event of the
fouled team's possession though the other team committed it (Q11), and `period_end` is the last
event of a possession the whistle interrupts (Q12). Cards, substitutions and the other match
events belong to no possession.

The simulator only emits on-ball events while play is live, so stopped time falls between a
possession's terminating event and the next restart, never inside a possession.
"""

from collections.abc import Sequence

from matchlens import calltrace
from matchlens.ingest import RecordReader
from matchlens.models import (
    Action,
    Event,
    Match,
    Outcome,
    Possession,
    PossessionOutcome,
    Zone,
    normalise_xy,
)
from matchlens.models.match_record import MATCH_EVENTS
from matchlens.understanding.shot_value import is_shot

# Each of these restarts follows the ball going out, so it ends any possession still open.
_OUT_OF_PLAY_RESTARTS = frozenset({Action.THROW_IN, Action.CORNER, Action.GOAL_KICK})


def sequence(reader: RecordReader, from_clock_ms: int, to_clock_ms: int) -> list[Possession]:
    """The possessions in `[from_clock_ms, to_clock_ms)`, in clock order.

    A possession still going at `to_clock_ms` is left out, because its outcome is not known yet.
    The first possession starts at the window's first on-ball event, so a window opening mid-way
    through a possession holds only its tail.
    """
    calltrace.entered("Understanding")
    match = reader.match
    possessions: list[Possession] = []
    current: list[Event] = []

    def close(outcome: PossessionOutcome, *terminator: Event) -> None:
        possessions.append(_possession(match, current, outcome, terminator))
        current.clear()

    for event in reader.events_between(from_clock_ms, to_clock_ms):
        if event.action is Action.PERIOD_END:
            if current:
                close(PossessionOutcome.PERIOD_END, event)
            continue
        if event.action in MATCH_EVENTS:
            continue
        if event.action is Action.FOUL:
            if current:
                close(PossessionOutcome.FOUL, event)
            continue
        if current and event.action in _OUT_OF_PLAY_RESTARTS:
            close(PossessionOutcome.OUT_OF_PLAY)  # e.g. a save turned behind: the corner says so
        elif current and event.team != current[0].team:
            close(PossessionOutcome.TURNOVER)
        current.append(event)
        if is_shot(event):
            close(PossessionOutcome.SHOT)
        elif event.outcome is Outcome.OUT_OF_PLAY:
            close(PossessionOutcome.OUT_OF_PLAY)
    return possessions


def _possession(
    match: Match, own: Sequence[Event], outcome: PossessionOutcome, terminator: Sequence[Event]
) -> Possession:
    first, last = own[0], own[-1]
    events = [*own, *terminator]
    assert first.team is not None  # on-ball events always have a team
    return Possession(
        possession_id=f"{match.match_id}-p{first.seq}",
        team=first.team,
        start_clock_ms=first.clock_ms,
        end_clock_ms=events[-1].clock_ms,
        pass_count=sum(e.action is Action.PASS for e in events),
        start_zone=_zone(match, first),
        end_zone=_zone(match, last),
        outcome=outcome,
        event_ids=tuple(e.event_id for e in events),
    )


def _zone(match: Match, event: Event) -> Zone:
    """The third `event` started in, from the acting team's view (it attacks towards +x)."""
    assert event.start_x is not None and event.start_y is not None
    team = next(t for t in match.teams if t.team_id == event.team)
    x, _ = normalise_xy(event.start_x, event.start_y, team.attack_direction(event.period))
    third = match.pitch_length_m / 6  # x runs from -length/2 to +length/2
    if x < -third:
        return Zone.DEFENSIVE_THIRD
    if x > third:
        return Zone.FINAL_THIRD
    return Zone.MIDDLE_THIRD
