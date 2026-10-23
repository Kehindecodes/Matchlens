"""D29's claims, built by rule from the frozen log and the readings (L7). No model.

Each moment type gets the claims D29 lists for it, in the order a lens that speaks only some of
them should hear them:

- goal: the scorer's goals, the score (or the team's goals while the other side has none, Q26
  2a), the build-up, the shot's quality
- chance: the run of big chances, the shot's quality
- tactical shift: the signal that fired, read as a judgement, then compared with the same team
  in the previous epoch and with the opponent at the same clock

Every operand cites the rows its value is counted from, and between them a moment's claims cite
every trigger that fired it (D22). A claim with nothing to cite is not made (invariant 5).
"""

import math
from collections.abc import Sequence

from matchlens.config import settings
from matchlens.models import (
    Action,
    Claim,
    ClaimType,
    Epoch,
    Event,
    Match,
    Metric,
    Moment,
    MomentType,
    Operand,
    Outcome,
    Ref,
    RefKind,
    SignalReading,
    Window,
)
from matchlens.understanding.possession import from_events
from matchlens.understanding.shot_value import is_shot, value

MODEL = "deterministic"
MODEL_VERSION = "claims-1"  # bump by hand whenever a rule below changes (invariant 7)

# How a possession wins the ball in open play; a restart is not winning it (D29).
_BALL_WINNING = frozenset({Action.TACKLE, Action.INTERCEPTION, Action.AERIAL_DUEL})


def explain_moment(
    moment: Moment,
    events: Sequence[Event],
    readings: Sequence[SignalReading],
    epochs: Sequence[Epoch],
    match: Match,
) -> list[Claim]:
    """The claims for `moment`. Every input is already frozen at the moment's clock."""
    if moment.type is MomentType.TACTICAL_SHIFT:
        operands = _shift(moment, readings, epochs, match)
    elif moment.type in (MomentType.GOAL, MomentType.CHANCE):
        trigger = next(e for e in events if e.event_id == moment.trigger_event_ids[0])
        if moment.type is MomentType.GOAL:
            operands = _goal(trigger, events, match)
        else:
            operands = _chance(trigger, events, match)
    else:
        operands = []
    return [
        _claim(moment, i, claim_type, ops, backing, threshold)
        for i, (claim_type, ops, backing, threshold) in enumerate(operands, start=1)
    ]


_Spec = tuple[ClaimType, tuple[Operand, ...], Ref | None, float | None]


def _claim(
    moment: Moment,
    n: int,
    claim_type: ClaimType,
    operands: tuple[Operand, ...],
    backing: Ref | None,
    threshold: float | None,
) -> Claim:
    return Claim(
        claim_id=f"{moment.moment_id}:c{n}",
        moment_id=moment.moment_id,
        claim_type=claim_type,
        operands=operands,
        backing_reading=backing,
        threshold=threshold,
        model=MODEL,
        model_version=MODEL_VERSION,
    )


def _descriptive(operand: Operand) -> _Spec:
    return ClaimType.DESCRIPTIVE, (operand,), None, None


def _comparative(subject: Operand, against: Operand) -> _Spec:
    return ClaimType.COMPARATIVE, (subject, against), None, None


def _events(events: Sequence[Event]) -> tuple[Ref, ...]:
    return tuple(Ref(kind=RefKind.EVENT, id=e.event_id) for e in events)


def _team(team_id: str) -> Ref:
    return Ref(kind=RefKind.TEAM, id=team_id)


def _opponent(match: Match, team_id: str) -> str:
    return next(t.team_id for t in match.teams if t.team_id != team_id)


# --- goals and chances ---------------------------------------------------------------------------


def _goals(subject: Ref, scored: Sequence[Event], clock_ms: int) -> Operand | None:
    """How many goals `subject` has by `clock_ms`, citing each one, or None if it has none."""
    if not scored:
        return None  # a count of nothing cites nothing, so it is not claimed (Q26 2a)
    return Operand(
        subject=subject,
        metric=Metric.GOALS,
        window=Window(start_ms=0, end_ms=clock_ms),
        value=float(len(scored)),
        evidence_ids=_events(scored),
    )


def _shot_quality(shot: Event, match: Match) -> Operand:
    return Operand(
        subject=_team(shot.team or ""),
        metric=Metric.SHOT_QUALITY,
        window=Window(start_ms=shot.clock_ms, end_ms=shot.clock_ms),
        value=value(shot, match).value,
        evidence_ids=_events([shot]),
    )


def _goal(goal: Event, events: Sequence[Event], match: Match) -> list[_Spec]:
    assert goal.team is not None  # a goal is an on-ball event
    goals = [e for e in events if e.outcome is Outcome.GOAL]
    specs: list[_Spec] = []
    if goal.player is not None:
        mine = [e for e in goals if e.player == goal.player]
        scorer = _goals(Ref(kind=RefKind.PLAYER, id=goal.player), mine, goal.clock_ms)
        assert scorer is not None  # this goal is one of them
        specs.append(_descriptive(scorer))

    team = _goals(_team(goal.team), [e for e in goals if e.team == goal.team], goal.clock_ms)
    opponent_id = _opponent(match, goal.team)
    against = _goals(_team(opponent_id), [e for e in goals if e.team == opponent_id], goal.clock_ms)
    assert team is not None
    specs.append(_comparative(team, against) if against is not None else _descriptive(team))

    if (build_up := _build_up(goal, events, match)) is not None:
        specs.append(_descriptive(build_up))
    specs.append(_descriptive(_shot_quality(goal, match)))
    return specs


def _build_up(shot: Event, events: Sequence[Event], match: Match) -> Operand | None:
    """The passes in the move that ended in `shot`, if the move began by winning the ball.

    A move begun by a restart has no claim: "a quick attack" reads the move's duration, which
    from a corner or a throw-in is not an attack's (D29).
    """
    move = next((p for p in from_events(match, events) if shot.event_id in p.event_ids), None)
    if move is None:
        return None
    first = next(e for e in events if e.event_id == move.event_ids[0])
    if first.action not in _BALL_WINNING:
        return None
    return Operand(
        subject=_team(move.team),
        metric=Metric.BUILD_UP_PASSES,
        window=Window(start_ms=move.start_clock_ms, end_ms=shot.clock_ms),
        value=float(move.pass_count),
        evidence_ids=tuple(Ref(kind=RefKind.EVENT, id=i) for i in move.event_ids),
    )


def _chance(shot: Event, events: Sequence[Event], match: Match) -> list[_Spec]:
    start = max(0, shot.clock_ms - settings.claim_chance_window_ms)
    big = [
        e
        for e in events
        if is_shot(e)
        and e.team == shot.team
        and start < e.clock_ms <= shot.clock_ms
        and value(e, match).value >= settings.spotter_chance_quality
    ]
    run = Operand(
        subject=_team(shot.team or ""),
        metric=Metric.CHANCES,
        window=Window(start_ms=start, end_ms=shot.clock_ms),
        value=float(len(big)),
        evidence_ids=_events(big),
    )
    return [_descriptive(run), _descriptive(_shot_quality(shot, match))]


# --- tactical shifts -----------------------------------------------------------------------------


def _reading(reading: SignalReading) -> Operand:
    return Operand(
        subject=_team(reading.team),
        metric=Metric(reading.signal.value),
        window=Window(start_ms=reading.clock_ms - reading.window_ms, end_ms=reading.clock_ms),
        value=reading.value,
        evidence_ids=(Ref(kind=RefKind.READING, id=reading.reading_id),),
    )


def _threshold(z_match: float) -> float | None:
    """The `z_match` the wording implies, signed: −2.0 reads "much less" (Q26 3a)."""
    size = abs(z_match)
    if size >= settings.claim_strong_z:
        return math.copysign(settings.claim_strong_z, z_match)
    if size >= settings.spotter_z_threshold:
        return math.copysign(settings.spotter_z_threshold, z_match)
    return None


def _shift(
    moment: Moment, readings: Sequence[SignalReading], epochs: Sequence[Epoch], match: Match
) -> list[_Spec]:
    fired = next(r for r in readings if r.reading_id == moment.trigger_reading_ids[0])
    now = _reading(fired)
    backing = Ref(kind=RefKind.READING, id=fired.reading_id)
    specs: list[_Spec] = []
    if (threshold := _threshold(fired.z_match)) is not None:
        specs.append((ClaimType.INTERPRETIVE, (now,), backing, threshold))

    same_series = [r for r in readings if r.signal is fired.signal and r.team == fired.team]
    previous = _previous_epoch(fired.epoch_id, epochs)
    earlier = [r for r in same_series if previous is not None and r.epoch_id == previous]
    if earlier:
        specs.append(_comparative(now, _reading(earlier[-1])))

    opponent_id = _opponent(match, fired.team)
    theirs = [
        r
        for r in readings
        if r.signal is fired.signal and r.team == opponent_id and r.clock_ms == fired.clock_ms
    ]
    if theirs:
        specs.append(_comparative(now, _reading(theirs[-1])))
    return specs


def _previous_epoch(epoch_id: str, epochs: Sequence[Epoch]) -> str | None:
    """The epoch before `epoch_id`, or None in the opening epoch."""
    ids = [e.epoch_id for e in epochs]
    i = ids.index(epoch_id) if epoch_id in ids else 0
    return ids[i - 1] if i > 0 else None
