"""Epochs: stretches of constant game state, cut at every structural break (U5).

The opening epoch starts at the first `period_start` with no trigger. A new one starts at a goal,
a red card, or the start of each later period. The score and the player counts at each start are
recomputed from the log every time (D16), counting everything up to and including that clock, so
a goal's epoch already shows the goal. Breaks at the same clock make one epoch, triggered by the
first of them. Only a red card changes a player count; substitutions and yellows do not.
"""

from collections.abc import Sequence

from matchlens import calltrace
from matchlens.ingest import RecordReader
from matchlens.models import Action, Epoch, EpochTrigger, Event, Outcome

_WHOLE_LOG_MS = 2**62  # past any match clock, so `events_between` returns everything


def detect(reader: RecordReader) -> list[Epoch]:
    """Every epoch in the log so far, in clock order. A pure function of the log."""
    calltrace.entered("Understanding")
    events = reader.events_between(0, _WHOLE_LOG_MS)
    starts = [e for e in events if e.action is Action.PERIOD_START]
    if not starts:
        return []
    boundaries: dict[int, EpochTrigger | None] = {starts[0].clock_ms: None}
    for event in events:
        trigger = _trigger(event)
        if trigger is not None:
            boundaries.setdefault(event.clock_ms, trigger)
    return [
        _epoch(reader, events, n, clock, trigger)
        for n, (clock, trigger) in enumerate(sorted(boundaries.items()))
    ]


def _trigger(event: Event) -> EpochTrigger | None:
    if event.outcome is Outcome.GOAL:
        return EpochTrigger.GOAL
    if event.action is Action.RED_CARD:
        return EpochTrigger.RED_CARD
    if event.action is Action.PERIOD_START and event.period > 1:
        return EpochTrigger.HALF_TIME
    return None


def _epoch(
    reader: RecordReader,
    events: Sequence[Event],
    n: int,
    clock_ms: int,
    trigger: EpochTrigger | None,
) -> Epoch:
    teams = [t.team_id for t in reader.match.teams]
    so_far = [e for e in events if e.clock_ms <= clock_ms]
    score = {t: sum(e.team == t and e.outcome is Outcome.GOAL for e in so_far) for t in teams}
    starters = {t: sum(p.team_id == t and p.is_starter for p in reader.players) for t in teams}
    sent_off = {t: sum(e.team == t and e.action is Action.RED_CARD for e in so_far) for t in teams}
    return Epoch(
        epoch_id=f"{reader.match.match_id}-epoch{n}",
        match_id=reader.match.match_id,
        start_clock_ms=clock_ms,
        score_state=score,
        player_counts={t: starters[t] - sent_off[t] for t in teams},
        trigger=trigger,
    )
