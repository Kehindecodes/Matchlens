"""The six checks. Each judges one claim and says why when it fails.

`value` and `entailment` are the line to hold (D21). `value` recomputes each operand from the
**record**, ignoring what the claim cited, and catches a wrong number. `entailment` reads only
the claim's **own evidence**, and catches a right number whose citations have nothing to do with
it. They share the metric definitions (D30) and nothing else: neither looks at what the other
reads.
"""

import math
from collections.abc import Sequence

from matchlens.config import settings
from matchlens.ingest import on_pitch_across
from matchlens.models import (
    Action,
    CheckResult,
    CheckStatus,
    Claim,
    Event,
    Metric,
    Moment,
    Operand,
    Outcome,
    Ref,
    RefKind,
    SignalReading,
)
from matchlens.understanding.buildup import (
    BALL_WINNING,
    assist_of,
    losses,
    shot_distance,
    stopper_of,
    win_third,
)
from matchlens.understanding.possession import from_events
from matchlens.understanding.shot_value import is_shot, value
from matchlens.verification.record import Record

PASSED = CheckResult(status=CheckStatus.PASSED)

_COUNTS = frozenset(
    {
        Metric.GOALS,
        Metric.CHANCES,
        Metric.BUILD_UP_PASSES,
        Metric.BALL_WON_THIRD,
        Metric.BALL_LOST,
        Metric.BALL_LOST_BY_KEEPER,
        Metric.ASSIST,
        Metric.SHOT_SAVED_BY,
        Metric.SHOT_BLOCKED_BY,
    }
)
_SIGNALS = frozenset(
    {Metric.TERRITORY, Metric.POSSESSION_CONTROL, Metric.PRESSING_INTENSITY, Metric.CHANCE_QUALITY}
)


def failed(reason: str) -> CheckResult:
    return CheckResult(status=CheckStatus.FAILED, reason=reason)


def same(metric: Metric, claimed: float, actual: float) -> bool:
    """Counts exactly, every other value within `value_rel_tolerance` (Q35: A)."""
    if metric in _COUNTS:
        return claimed == actual
    return math.isclose(claimed, actual, rel_tol=settings.value_rel_tolerance, abs_tol=1e-12)


def _refs(claim: Claim) -> list[Ref]:
    refs = [ref for o in claim.operands for ref in o.evidence_ids]
    if claim.backing_reading is not None:
        refs.append(claim.backing_reading)
    return refs


def _resolve(ref: Ref, record: Record) -> Event | SignalReading | None:
    if ref.kind is RefKind.EVENT:
        return record.event.get(ref.id)
    if ref.kind is RefKind.READING:
        return record.reading.get(ref.id)
    return None  # a run is not built in v1, so nothing can resolve one


def _what(o: Operand) -> str:
    return f"{o.subject.id}'s {o.metric} over {o.window.start_ms}–{o.window.end_ms} ms"


# --- citation, temporal, entity ------------------------------------------------------------------


def citation(claim: Claim, record: Record) -> CheckResult:
    """Every ref the claim cites resolves to a real row."""
    missing = [f"{r.kind} {r.id}" for r in _refs(claim) if _resolve(r, record) is None]
    if missing:
        return failed(f"cites rows that are not in the record: {', '.join(missing)}")
    return PASSED


def temporal(claim: Claim, moment: Moment, record: Record) -> CheckResult:
    """Nothing cited, and no window, runs past the moment's clock. Inclusive: the clock is in."""
    late = [
        f"{r.kind} {r.id} at {row.clock_ms} ms"
        for r in _refs(claim)
        if (row := _resolve(r, record)) is not None and row.clock_ms > moment.clock_ms
    ]
    late += [
        f"{_what(o)}, which ends after it"
        for o in claim.operands
        if o.window.end_ms > moment.clock_ms
    ]
    if late:
        return failed(f"after the moment's clock of {moment.clock_ms} ms: {'; '.join(late)}")
    return PASSED


def entity(claim: Claim, record: Record) -> CheckResult:
    """A player subject was on the pitch across his operand's window. Teams have no such check."""
    players = [o for o in claim.operands if o.subject.kind is RefKind.PLAYER]
    if not players:
        return CheckResult(status=CheckStatus.NOT_APPLICABLE, reason="every subject is a team")
    for o in players:
        player = record.player.get(o.subject.id)
        if player is None:
            return failed(f"{o.subject.id} is not on either roster")
        events = record.until(o.window.end_ms)
        if not on_pitch_across(player, events, o.window.start_ms, o.window.end_ms):
            return failed(f"{player.name} was not on the pitch across {_what(o)}")
    return PASSED


# --- value: from the record ----------------------------------------------------------------------


class _Unrecomputable(ValueError):
    pass


def _team_only(o: Operand) -> str:
    if o.subject.kind is not RefKind.TEAM:
        raise _Unrecomputable(f"{o.metric} is a team's, not a {o.subject.kind}'s")
    return o.subject.id


def recompute(o: Operand, record: Record) -> list[float]:
    """What the record says `o`'s value is, read without its evidence (D30's definitions).

    A list because one shot's quality can have two candidates, two shots in one millisecond.
    Raises `_Unrecomputable` when the record holds nothing the operand could be measuring.
    """
    start, end = o.window.start_ms, o.window.end_ms
    match = record.match
    if o.metric is Metric.GOALS:
        key = "player" if o.subject.kind is RefKind.PLAYER else "team"
        return [
            float(
                sum(
                    e.outcome is Outcome.GOAL
                    and getattr(e, key) == o.subject.id
                    and start <= e.clock_ms <= end
                    for e in record.events
                )
            )
        ]
    if o.metric in (Metric.BALL_LOST, Metric.BALL_LOST_BY_KEEPER):
        return [_ball_lost(o, record)]
    if o.metric in (Metric.ASSIST, Metric.SHOT_SAVED_BY, Metric.SHOT_BLOCKED_BY):
        return [_around_a_shot(o, record)]
    team = _team_only(o)
    if o.metric is Metric.BALL_WON_THIRD:
        wins = [
            e
            for e in record.events
            if e.team == team and e.action in BALL_WINNING and e.clock_ms == end == start
        ]
        if not wins:
            raise _Unrecomputable(f"{team} won no ball at {end} ms")
        return [float(win_third(match, e)) for e in wins]
    if o.metric is Metric.SHOT_DISTANCE:
        shots = [e for e in record.events if is_shot(e) and e.team == team and e.clock_ms == end]
        if start != end or not shots:
            raise _Unrecomputable(f"no shot by {team} at {end} ms")
        return [shot_distance(match, e) for e in shots]
    if o.metric is Metric.CHANCES:
        bar = settings.spotter_chance_quality
        return [
            float(
                sum(
                    is_shot(e)
                    and e.team == team
                    and start < e.clock_ms <= end
                    and value(e, match).value >= bar
                    for e in record.events
                )
            )
        ]
    if o.metric is Metric.SHOT_QUALITY:
        shots = [e for e in record.events if is_shot(e) and e.team == team and e.clock_ms == end]
        if start != end or not shots:
            raise _Unrecomputable(f"no shot by {team} at {end} ms")
        return [value(e, match).value for e in shots]
    if o.metric is Metric.BUILD_UP_PASSES:
        events = record.until(end)
        shots = {e.event_id for e in events if is_shot(e) and e.team == team and e.clock_ms == end}
        moves = [
            p
            for p in from_events(match, events)
            if p.team == team and p.start_clock_ms == start and shots & set(p.event_ids)
        ]
        if not moves:
            raise _Unrecomputable(f"no move by {team} from {start} ms ending in a shot at {end} ms")
        return [float(p.pass_count) for p in moves]
    readings = [
        r
        for r in record.readings
        if r.signal.value == o.metric.value
        and r.team == team
        and r.clock_ms == end
        and r.clock_ms - r.window_ms == start
    ]
    if not readings:
        raise _Unrecomputable(f"no {o.metric} reading for {team} over {start}–{end} ms")
    return [r.value for r in readings]


def _around_a_shot(o: Operand, record: Record) -> float:
    """1 if the record says `o`'s player set a shot up, saved it or blocked it, in its window.

    The window runs from the player's event to the shot, for an assist, or from the shot to the
    player's event, for a save or a block.
    """
    if o.subject.kind is not RefKind.PLAYER:
        raise _Unrecomputable(f"{o.metric} is a player's, not a {o.subject.kind}'s")
    start, end = o.window.start_ms, o.window.end_ms
    for shot in record.events:
        if not is_shot(shot):
            continue
        if o.metric is Metric.ASSIST:
            pass_ = assist_of(record.events, shot)
            if (
                pass_
                and pass_.player == o.subject.id
                and (pass_.clock_ms, shot.clock_ms) == (start, end)
            ):
                return 1.0
            continue
        stop = stopper_of(record.events, shot)
        wanted = Action.SAVE if o.metric is Metric.SHOT_SAVED_BY else Action.BLOCK
        if (
            stop
            and stop.player == o.subject.id
            and stop.action is wanted
            and (shot.clock_ms, stop.clock_ms) == (start, end)
        ):
            return 1.0
    return 0.0


def _ball_lost(o: Operand, record: Record) -> float:
    """1 if the record says `o`'s player gave the ball away at its clock, else 0.

    For a keeper's, the player has to be a goalkeeper."""
    if o.subject.kind is not RefKind.PLAYER:
        raise _Unrecomputable(f"{o.metric} is a player's, not a {o.subject.kind}'s")
    keeper = record.player.get(o.subject.id)
    if o.metric is Metric.BALL_LOST_BY_KEEPER and (keeper is None or keeper.position != "GK"):
        return 0.0
    end = o.window.end_ms
    # The whole record, not the events up to the loss: a loss is only one when the other side
    # takes the ball next, and that event comes after it.
    gave = (
        lost.player == o.subject.id and lost.clock_ms == end
        for _, lost in losses(record.match, record.events)
    )
    return float(any(gave))  # two moves can follow one loss; it is still one loss


def value_(claim: Claim, record: Record) -> tuple[CheckResult, tuple[float, ...]]:
    """Each operand recomputed from the record and compared: the check, and one figure each.

    A figure that cannot be recomputed is NaN in `recomputed_value`, with the reason.
    """
    figures: list[float] = []
    wrong: list[str] = []
    for o in claim.operands:
        try:
            candidates = recompute(o, record)
        except _Unrecomputable as nothing:
            figures.append(math.nan)
            wrong.append(f"{_what(o)}: {nothing}")
            continue
        actual = min(candidates, key=lambda c: abs(c - o.value))
        figures.append(actual)
        if not same(o.metric, o.value, actual):
            wrong.append(f"{_what(o)} is {actual:g} in the record, not {o.value:g}")
    if wrong:
        return failed("; ".join(wrong)), tuple(figures)
    return PASSED, tuple(figures)


# --- entailment: from the claim's own evidence ---------------------------------------------------


def _supports(o: Operand, record: Record) -> str | None:
    """Why `o`'s own evidence does not support it, or None if it does (D21: one rule)."""
    rows = [_resolve(r, record) for r in o.evidence_ids]
    if any(row is None for row in rows):
        return "some of its evidence does not exist"
    events = [row for row in rows if isinstance(row, Event)]
    readings = [row for row in rows if isinstance(row, SignalReading)]
    start, end = o.window.start_ms, o.window.end_ms
    subject = o.subject.id

    if o.metric in _SIGNALS:
        if events or len(readings) != 1:
            return "a signal's value is one reading, and nothing else"
        [r] = readings
        if r.signal.value != o.metric.value or r.team != subject:
            return f"cites {r.team}'s {r.signal} reading"
        if (r.clock_ms - r.window_ms, r.clock_ms) != (start, end):
            return "cites a reading over a different window"
        if not same(o.metric, o.value, r.value):
            return f"its reading says {r.value:g}"
        return None

    if readings:
        return f"{o.metric} is counted from events, but it cites a reading"
    if o.metric is Metric.GOALS:
        key = "player" if o.subject.kind is RefKind.PLAYER else "team"
        off = [e.event_id for e in events
               if e.outcome is not Outcome.GOAL or getattr(e, key) != subject
               or not start <= e.clock_ms <= end]  # fmt: skip
        if off:
            return f"cites events that are not {subject}'s goals in the window: {', '.join(off)}"
        counted = float(len(events))
    elif o.metric in (Metric.BALL_LOST, Metric.BALL_LOST_BY_KEEPER):
        if len(events) != 1 or events[0].player != subject or events[0].clock_ms != end:
            return f"a loss cites that one event by {subject} at {end} ms"
        counted = 1.0
    elif o.metric is Metric.ASSIST:
        if len(events) != 2 or not is_shot(events[1]) or events[0].player != subject:
            return f"an assist cites the pass by {subject} and the shot it set up"
        if (events[0].clock_ms, events[1].clock_ms) != (start, end):
            return "cites a pass and a shot at other clocks"
        counted = 1.0 if assist_of(events, events[1]) is not None else 0.0
    elif o.metric in (Metric.SHOT_SAVED_BY, Metric.SHOT_BLOCKED_BY):
        wanted = Action.SAVE if o.metric is Metric.SHOT_SAVED_BY else Action.BLOCK
        if len(events) != 2 or not is_shot(events[0]) or events[1].player != subject:
            return f"a stop cites the shot and the event by {subject} that stopped it"
        if events[1].action is not wanted or (events[0].clock_ms, events[1].clock_ms) != (
            start,
            end,
        ):
            return "cites a shot and a stop that do not match"
        counted = 1.0 if events[1].team != events[0].team else 0.0
    elif o.metric is Metric.BALL_WON_THIRD:
        if len(events) != 1 or events[0].team != subject or events[0].action not in BALL_WINNING:
            return f"a win cites that one ball-winning event by {subject}"
        if events[0].clock_ms != end:
            return "cites a win at another clock"
        counted = float(win_third(record.match, events[0]))
    elif o.metric is Metric.SHOT_DISTANCE:
        if len(events) != 1 or not is_shot(events[0]) or events[0].team != subject:
            return f"a shot's distance cites that one shot by {subject}"
        if events[0].clock_ms != end:
            return "cites a shot at another clock"
        counted = shot_distance(record.match, events[0])
    elif o.metric is Metric.CHANCES:
        bar = settings.spotter_chance_quality
        off = [e.event_id for e in events
               if not is_shot(e) or e.team != subject or not start < e.clock_ms <= end
               or value(e, record.match).value < bar]  # fmt: skip
        if off:
            return (
                f"cites events that are not {subject}'s big chances in the window: {', '.join(off)}"
            )
        counted = float(len(events))
    elif o.metric is Metric.SHOT_QUALITY:
        if len(events) != 1 or not is_shot(events[0]) or events[0].team != subject:
            return f"a shot's quality cites that one shot by {subject}"
        if events[0].clock_ms != end:
            return "cites a shot at another clock"
        counted = value(events[0], record.match).value
    else:  # build_up_passes
        off = [e.event_id for e in events if e.team != subject or not start <= e.clock_ms <= end]
        if off:
            return f"cites events outside {subject}'s move: {', '.join(off)}"
        counted = float(sum(e.action is Action.PASS for e in events))
    if not same(o.metric, o.value, counted):
        return f"its evidence counts {counted:g}"
    return None


def entailment(claim: Claim, record: Record) -> CheckResult:
    """Each operand's evidence supports it; an interpretive claim's reading clears its threshold."""
    wrong = [f"{_what(o)}: {why}" for o in claim.operands if (why := _supports(o, record))]
    if claim.backing_reading is not None and claim.threshold is not None:
        backing = record.reading.get(claim.backing_reading.id)
        [o] = claim.operands
        if backing is None:
            wrong.append("its backing reading does not exist")
        elif claim.backing_reading not in o.evidence_ids:
            wrong.append("its backing reading is not the reading it interprets")
        elif math.copysign(1, backing.z_match) != math.copysign(1, claim.threshold) or abs(
            backing.z_match
        ) < abs(claim.threshold):
            wrong.append(
                f"the reading's z_match is {backing.z_match:.2f}, "
                f"which does not clear the threshold {claim.threshold:+g}"
            )
    if wrong:
        return failed("; ".join(wrong))
    return PASSED


# --- coverage: across the moment's claims --------------------------------------------------------


def coverage(moment: Moment, claims: Sequence[Claim]) -> CheckResult:
    """Every trigger that fired the moment is in some claim's evidence (D22).

    A property of the moment, so every claim of it gets the same answer.
    """
    cited = {ref.id for c in claims for ref in _refs(c)}
    missing = [
        t for t in (*moment.trigger_reading_ids, *moment.trigger_event_ids) if t not in cited
    ]
    if missing:
        return failed(f"no claim of the moment cites its trigger {', '.join(missing)}")
    return PASSED
