"""How a goal or a chance came about, as numbers the event log can recount (D30).

Three facts the viewer cannot read off the picture: where the ball was won, who gave it away,
and how far out the shot was struck. Each is one function of the log, shared by the claim
builder that states it and the verifier that recounts it, so they cannot drift apart.

- `win_third` is the third the ball-winning event started in, from the winner's side: 1 their own,
  2 the middle, 3 the opponent's. It is `possession.zone`, the definition Possessions use.
- `ball_loser` is the player whose on-ball event ended the other side's possession by turnover,
  the event just before the move began. A possession that ended any other way (a foul, the ball
  out of play) has no loser: the side did not give the ball away to the other.
- `shot_distance` is `shot_value`'s distance from the centre of the goal attacked, to a decimal.
- `assist_of` is the completed pass, by a team-mate, that was the event just before the shot and
  went to the shooter. A shot the shooter made after carrying the ball himself has none.
- `stopper_of` is the keeper's save or the defender's block that was the next event after a shot.
  A shot that went wide or in has none.
"""

from collections.abc import Sequence

from matchlens.models import (
    Action,
    Event,
    Match,
    Outcome,
    Possession,
    PossessionOutcome,
    Zone,
)
from matchlens.understanding.possession import from_events, zone
from matchlens.understanding.shot_value import value

# How a possession wins the ball in open play; a restart is not winning it (D30).
BALL_WINNING = frozenset({Action.TACKLE, Action.INTERCEPTION, Action.AERIAL_DUEL})

_THIRD = {Zone.DEFENSIVE_THIRD: 1, Zone.MIDDLE_THIRD: 2, Zone.FINAL_THIRD: 3}


def win_third(match: Match, event: Event) -> int:
    """The third, 1 to 3 from the winner's own, that `event` started in."""
    return _THIRD[zone(match, event)]


def shot_distance(match: Match, shot: Event) -> float:
    """Metres from the centre of the goal attacked, to one decimal place."""
    return round(value(shot, match).distance, 1)


def losses(match: Match, events: Sequence[Event]) -> list[tuple[Possession, Event]]:
    """Every move that began by taking the ball off the other side, with the event that gave it.

    The event is the last on-ball event of the possession before the move, which ended in a
    turnover by the other side. A move that follows a foul, the ball going out, or its own side's
    possession has no such event and is not listed.
    """
    possessions = from_events(match, events)
    by_id = {e.event_id: e for e in events}
    found = []
    for previous, move in zip(possessions, possessions[1:], strict=False):
        if previous.team == move.team or previous.outcome is not PossessionOutcome.TURNOVER:
            continue
        last = by_id[previous.event_ids[-1]]
        if last.player is not None:
            found.append((move, last))
    return found


def ball_loser(match: Match, events: Sequence[Event], move: Possession) -> Event | None:
    """The event that gave the ball away to `move`, or None."""
    return next(
        (lost for m, lost in losses(match, events) if m.possession_id == move.possession_id), None
    )


def assist_of(events: Sequence[Event], shot: Event) -> Event | None:
    """The pass that set `shot` up, or None."""
    index = next((i for i, e in enumerate(events) if e.event_id == shot.event_id), 0)
    if index == 0:
        return None
    pass_ = events[index - 1]
    if (
        pass_.action is Action.PASS
        and pass_.outcome is Outcome.COMPLETE
        and pass_.team == shot.team
        and pass_.receiver == shot.player
        and pass_.player not in (None, shot.player)
    ):
        return pass_
    return None


def stopper_of(events: Sequence[Event], shot: Event) -> Event | None:
    """The save or block that was the next event after `shot`, or None."""
    index = next((i for i, e in enumerate(events) if e.event_id == shot.event_id), None)
    if index is None or index + 1 >= len(events):
        return None
    after = events[index + 1]
    if after.team != shot.team and after.action in (Action.SAVE, Action.BLOCK):
        return after if after.player is not None else None
    return None
