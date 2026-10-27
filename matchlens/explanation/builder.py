"""D30's claims, built by rule from the frozen log and the readings (L7). No model.

Each moment type gets the claims D30 lists for it, in the order a lens that speaks only some of
them should hear them:

- goal: the scorer's goals, the score (or the team's goals while the other side has none, Q26
  2a), how it came about (the build-up, where the ball was won, how fast it was regained, who
  gave it away, a switch of play, a quick combination, how far out the shot was), what the
  positions showed (an overload, a decoy run, an early run), who set it up, the shot's quality
- chance: the run of big chances, the run set against the opponent's over the same window when
  they had one too, how it came about, what the positions showed, who saved or blocked it, the
  shot's quality
- tactical shift: the signal that fired, read as a judgement, then compared with the same team
  in the previous epoch and with the opponent at the same clock

Every operand cites the rows its value is counted from, and between them a moment's claims cite
every trigger that fired it (D22). A claim with nothing to cite is not made (invariant 5). What
the positions showed is cited as the `PositionReading` Understanding took for the shot, never as
a frame (invariant 1, Q48).
"""

import math
from collections.abc import Sequence

from matchlens.config import settings
from matchlens.ingest.roster import pitch_window
from matchlens.models import (
    Action,
    Claim,
    ClaimType,
    Epoch,
    Event,
    Match,
    Mechanism,
    Metric,
    Moment,
    MomentType,
    Operand,
    Outcome,
    Player,
    PositionReading,
    Ref,
    RefKind,
    SignalReading,
    Window,
)
from matchlens.understanding.buildup import (
    BALL_WINNING,
    assist_of,
    ball_loser,
    combination_of,
    lateral,
    regain_of,
    shot_distance,
    stopper_of,
    switch_of,
    win_third,
)
from matchlens.understanding.possession import from_events
from matchlens.understanding.shot_value import is_shot, value

MODEL = "deterministic"
MODEL_VERSION = "claims-7"  # bump by hand whenever a rule below changes (invariant 7)


def explain_moment(
    moment: Moment,
    events: Sequence[Event],
    readings: Sequence[SignalReading],
    epochs: Sequence[Epoch],
    match: Match,
    players: Sequence[Player],
    positions: Sequence[PositionReading] = (),
) -> list[Claim]:
    """The claims for `moment`. Every input is already frozen at the moment's clock."""
    if moment.type is MomentType.TACTICAL_SHIFT:
        operands = _shift(moment, readings, epochs, match)
    elif moment.type in (MomentType.GOAL, MomentType.CHANCE):
        trigger = next(e for e in events if e.event_id == moment.trigger_event_ids[0])
        shown = [p for p in positions if p.shot_id == trigger.event_id]
        if moment.type is MomentType.GOAL:
            operands = _goal(trigger, events, match, players, shown)
        else:
            operands = _chance(trigger, events, match, players, shown)
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


def _goals(
    subject: Ref, scored: Sequence[Event], clock_ms: int, since_ms: int = 0
) -> Operand | None:
    """How many goals `subject` has from `since_ms` to `clock_ms`, citing each one, or None if
    it has none."""
    if not scored:
        return None  # a count of nothing cites nothing, so it is not claimed (Q26 2a)
    return Operand(
        subject=subject,
        metric=Metric.GOALS,
        window=Window(start_ms=since_ms, end_ms=clock_ms),
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


def _goal(
    goal: Event,
    events: Sequence[Event],
    match: Match,
    players: Sequence[Player],
    positions: Sequence[PositionReading],
) -> list[_Spec]:
    assert goal.team is not None  # a goal is an on-ball event
    goals = [e for e in events if e.outcome is Outcome.GOAL]
    specs: list[_Spec] = []
    if goal.player is not None:
        mine = [e for e in goals if e.player == goal.player]
        # A player's count runs from when he came on, so the window is all time on the pitch
        # and `entity` can check him across it (Q36: B).
        player = next(p for p in players if p.player_id == goal.player)
        entered, _ = pitch_window(player, events)
        scorer = _goals(Ref(kind=RefKind.PLAYER, id=goal.player), mine, goal.clock_ms, entered)
        assert scorer is not None  # this goal is one of them
        specs.append(_descriptive(scorer))

    team = _goals(_team(goal.team), [e for e in goals if e.team == goal.team], goal.clock_ms)
    opponent_id = _opponent(match, goal.team)
    against = _goals(_team(opponent_id), [e for e in goals if e.team == opponent_id], goal.clock_ms)
    assert team is not None
    specs.append(_comparative(team, against) if against is not None else _descriptive(team))

    specs.extend(_descriptive(operand) for operand in _how(goal, events, match, players))
    specs.extend(_moved(match, positions))
    if (assist := _assist(goal, events)) is not None:
        specs.append(_descriptive(assist))
    specs.append(_descriptive(_shot_quality(goal, match)))
    return specs


def _how(
    shot: Event, events: Sequence[Event], match: Match, players: Sequence[Player]
) -> list[Operand]:
    """How `shot` came about, as the facts the log can recount: the move that ended in it, where
    that move won the ball, who gave the ball away, and how far out the shot was struck.

    A move begun by a restart has no first three: "a quick attack" reads the move's duration,
    which from a corner or a throw-in is not an attack's, and there is no loss to point at (D30).
    """
    operands: list[Operand] = []
    move = next((p for p in from_events(match, events) if shot.event_id in p.event_ids), None)
    if move is not None:
        first = next(e for e in events if e.event_id == move.event_ids[0])
        if first.action in BALL_WINNING:
            operands.append(
                Operand(
                    subject=_team(move.team),
                    metric=Metric.BUILD_UP_PASSES,
                    window=Window(start_ms=move.start_clock_ms, end_ms=shot.clock_ms),
                    value=float(move.pass_count),
                    evidence_ids=tuple(Ref(kind=RefKind.EVENT, id=i) for i in move.event_ids),
                )
            )
            operands.append(
                Operand(
                    subject=_team(move.team),
                    metric=Metric.BALL_WON_THIRD,
                    window=Window(start_ms=first.clock_ms, end_ms=first.clock_ms),
                    value=float(win_third(match, first)),
                    evidence_ids=_events([first]),
                )
            )
            if (regained := regain_of(match, events, move)) is not None:
                lost_it, won_it = regained
                operands.append(
                    Operand(
                        subject=_team(move.team),
                        metric=Metric.REGAIN,
                        window=Window(start_ms=lost_it.clock_ms, end_ms=won_it.clock_ms),
                        value=(won_it.clock_ms - lost_it.clock_ms) / 1000,
                        evidence_ids=_events([lost_it, won_it]),
                    )
                )
            if (lost := ball_loser(match, events, move)) is not None:
                assert lost.player is not None  # `ball_loser` only returns an event with a player
                keeper = any(p.player_id == lost.player and p.position == "GK" for p in players)
                metric = (
                    Metric.BALL_LOST_BY_KEEPER
                    if keeper
                    else Metric.PRESSURED_LOSS
                    if lost.under_pressure
                    else Metric.BALL_LOST
                )
                operands.append(
                    Operand(
                        subject=Ref(kind=RefKind.PLAYER, id=lost.player),
                        metric=metric,
                        window=Window(start_ms=lost.clock_ms, end_ms=lost.clock_ms),
                        value=1.0,
                        evidence_ids=_events([lost]),
                    )
                )
    if move is not None and (switch := switch_of(events, move)) is not None:
        width = lateral(switch)
        assert width is not None  # `switch_of` only returns a pass with positions
        operands.append(
            Operand(
                subject=_team(move.team),
                metric=Metric.SWITCH_OF_PLAY,
                window=Window(start_ms=switch.clock_ms, end_ms=switch.clock_ms),
                value=width,
                evidence_ids=_events([switch]),
            )
        )
    if (passes := combination_of(events, shot)) is not None:
        operands.append(
            Operand(
                subject=_team(shot.team or ""),
                metric=Metric.COMBINATION,
                window=Window(start_ms=passes[0].clock_ms, end_ms=shot.clock_ms),
                value=3.0,
                evidence_ids=_events([*passes, shot]),
            )
        )
    operands.append(
        Operand(
            subject=_team(shot.team or ""),
            metric=Metric.SHOT_DISTANCE,
            window=Window(start_ms=shot.clock_ms, end_ms=shot.clock_ms),
            value=shot_distance(match, shot),
            evidence_ids=_events([shot]),
        )
    )
    return operands


def _moved(match: Match, positions: Sequence[PositionReading]) -> list[_Spec]:
    """What the frames showed before the shot, one claim per position reading, each citing it.

    An overload is the attackers set against the defenders near the ball. A decoy run is said of
    the team-mate who made it, and an early run of the shooter: the defender a decoy drew is in
    the reading, and not in the claim, so no card names him.
    """
    specs: list[_Spec] = []
    for reading in sorted(positions, key=lambda p: p.mechanism.value):
        cited = (Ref(kind=RefKind.POSITION, id=reading.reading_id),)
        window = Window(start_ms=reading.start_ms, end_ms=reading.end_ms)
        if reading.mechanism is Mechanism.OVERLOAD:
            assert reading.against is not None  # an overload always counts both sides
            specs.append(
                _comparative(
                    Operand(
                        subject=_team(reading.team),
                        metric=Metric.OVERLOAD,
                        window=window,
                        value=reading.value,
                        evidence_ids=cited,
                    ),
                    Operand(
                        subject=_team(_opponent(match, reading.team)),
                        metric=Metric.OVERLOAD,
                        window=window,
                        value=reading.against,
                        evidence_ids=cited,
                    ),
                )
            )
            continue
        assert reading.player is not None  # a run is always someone's
        metric = Metric.DECOY_RUN if reading.mechanism is Mechanism.DECOY_RUN else Metric.EARLY_RUN
        specs.append(
            _descriptive(
                Operand(
                    subject=Ref(kind=RefKind.PLAYER, id=reading.player),
                    metric=metric,
                    window=window,
                    value=reading.value,
                    evidence_ids=cited,
                )
            )
        )
    return specs


def _big_chances(
    team_id: str, shot: Event, events: Sequence[Event], match: Match
) -> Operand | None:
    """`team_id`'s big chances over the chances window ending at `shot`, citing each, or None."""
    start = max(0, shot.clock_ms - settings.claim_chance_window_ms)
    big = [
        e
        for e in events
        if is_shot(e)
        and e.team == team_id
        and start < e.clock_ms <= shot.clock_ms
        and value(e, match).value >= settings.spotter_chance_quality
    ]
    if not big:
        return None  # a count of nothing cites nothing (Q26 2a)
    return Operand(
        subject=_team(team_id),
        metric=Metric.CHANCES,
        window=Window(start_ms=start, end_ms=shot.clock_ms),
        value=float(len(big)),
        evidence_ids=_events(big),
    )


def _assist(goal: Event, events: Sequence[Event]) -> Operand | None:
    """The pass that set `goal` up, citing it and the goal, or None if he carried it in."""
    pass_ = assist_of(events, goal)
    if pass_ is None:
        return None
    assert pass_.player is not None  # `assist_of` only returns a pass with a player
    return Operand(
        subject=Ref(kind=RefKind.PLAYER, id=pass_.player),
        metric=Metric.ASSIST,
        window=Window(start_ms=pass_.clock_ms, end_ms=goal.clock_ms),
        value=1.0,
        evidence_ids=_events([pass_, goal]),
    )


def _stopped(shot: Event, events: Sequence[Event]) -> Operand | None:
    """The keeper who saved `shot` or the player who blocked it, citing the shot and the stop."""
    stop = stopper_of(events, shot)
    if stop is None or stop.player is None:
        return None
    return Operand(
        subject=Ref(kind=RefKind.PLAYER, id=stop.player),
        metric=Metric.SHOT_SAVED_BY if stop.action is Action.SAVE else Metric.SHOT_BLOCKED_BY,
        window=Window(start_ms=shot.clock_ms, end_ms=stop.clock_ms),
        value=1.0,
        evidence_ids=_events([shot, stop]),
    )


def _chance(
    shot: Event,
    events: Sequence[Event],
    match: Match,
    players: Sequence[Player],
    positions: Sequence[PositionReading],
) -> list[_Spec]:
    team_id = shot.team or ""
    run = _big_chances(team_id, shot, events, match)
    assert run is not None  # the shot that fired this moment is one of them
    specs = [_descriptive(run)]
    if (theirs := _big_chances(_opponent(match, team_id), shot, events, match)) is not None:
        specs.append(_comparative(run, theirs))
    specs.extend(_descriptive(operand) for operand in _how(shot, events, match, players))
    specs.extend(_moved(match, positions))
    if (stopped := _stopped(shot, events)) is not None:
        specs.append(_descriptive(stopped))
    specs.append(_descriptive(_shot_quality(shot, match)))
    return specs


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
