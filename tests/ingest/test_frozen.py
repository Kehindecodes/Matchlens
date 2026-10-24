"""A1: the frozen log serves the record at or before a moment's clock, and nothing after it."""

import enum

import pytest

from matchlens.ingest import FrameAccess, FrozenLog, Ingest, RecordReader
from matchlens.ingest.events import InMemoryEventRepository
from matchlens.ingest.frames import FrameWindow
from matchlens.models import (
    Epoch,
    Event,
    Frame,
    Moment,
    MomentType,
    Outcome,
    Ref,
    RefKind,
    SignalReading,
)
from matchlens.understanding import Understanding
from tests.source.helpers import Played

MIN = 60_000


class Run:
    def __init__(self, match: Played):
        self.ingest = Ingest()
        self.understanding = Understanding(self.ingest.record)
        self.readings: list[SignalReading] = []
        self._items = iter(match.items)

    def until(self, clock_ms: int) -> None:
        """Feed the stream up to the first event after `clock_ms`."""
        for item in self._items:
            self.ingest.accept(item)
            self.readings.extend(self.understanding.observe(item))
            if isinstance(item, Event) and item.clock_ms > clock_ms:
                return

    @property
    def epochs(self) -> tuple[Epoch, ...]:
        return self.understanding.epochs


@pytest.fixture(scope="module")
def whole(match_1: Played) -> Run:
    run = Run(match_1)
    run.until(match_1.end_clock_ms + 1)
    return run


def _moment(clock_ms: int, event: Event) -> Moment:
    return Moment(
        moment_id="m-test",
        clock_ms=clock_ms,
        type=MomentType.GOAL,
        subject=Ref(kind=RefKind.TEAM, id=event.team or "home"),
        importance=1.0,
        trigger_reading_ids=(),
        trigger_event_ids=(event.event_id,),
        epoch_id="e-test",
        model="test",
        model_version="0",
    )


def _first_goal(match: Played) -> Event:
    return next(e for e in match.events if e.outcome is Outcome.GOAL)


def _frozen(run: Run, moment: Moment) -> FrozenLog:
    return FrozenLog(moment, run.ingest.record(), run.readings, run.epochs)


def test_nothing_after_the_clock_comes_back(match_1: Played, whole: Run):
    # The weak version of V2, asked of the reader directly. The strong one is in the explainer's
    # tests, where a poisoned log must leave the claims byte-identical.
    goal = _first_goal(match_1)
    clock = goal.clock_ms
    log = _frozen(whole, _moment(clock, goal))
    assert log.events == tuple(e for e in match_1.events if e.clock_ms <= clock)
    assert log.readings == tuple(r for r in whole.readings if r.clock_ms <= clock)
    assert log.epochs == tuple(e for e in whole.epochs if e.start_clock_ms <= clock)
    # and there was a future it left out
    assert len(log.events) < len(match_1.events)
    assert len(log.readings) < len(whole.readings)
    assert len(log.epochs) < len(whole.epochs)


def test_the_event_at_the_clock_is_in_the_log(match_1: Played, whole: Run):
    # Inclusive (Q6): a goal moment's clock is its goal's, and the goal must be citable.
    goal = _first_goal(match_1)
    log = _frozen(whole, _moment(goal.clock_ms, goal))
    assert log.events[-1].clock_ms == goal.clock_ms
    assert goal in log.events
    # the epoch the goal starts begins at the clock too, and is in
    assert log.epochs[-1].start_clock_ms == goal.clock_ms


def test_one_millisecond_earlier_the_event_is_not(match_1: Played, whole: Run):
    goal = _first_goal(match_1)
    log = _frozen(whole, _moment(goal.clock_ms - 1, goal))
    assert goal not in log.events


def test_a_frozen_log_is_a_snapshot(match_1: Played):
    run = Run(match_1)
    run.until(10 * MIN)
    last = run.ingest.record().events_between(0, 10**9)[-1]
    log = _frozen(run, _moment(last.clock_ms, last))
    events, readings, epochs = log.events, log.readings, log.epochs

    run.until(match_1.end_clock_ms + 1)  # the rest of the match arrives after it was taken

    assert (log.events, log.readings, log.epochs) == (events, readings, epochs)
    assert len(run.ingest.record().events_between(0, 10**9)) > len(events)


# What a frozen log must not hold: a frame, anything that serves frames, or anything live that
# could serve it a later record than the one it was frozen with.
_BANNED = (Frame, FrameWindow, FrameAccess, Ingest, RecordReader, InMemoryEventRepository)
_LEAVES = (str, bytes, int, float, bool, type(None), enum.Enum)


def _reachable(root: object) -> list[object]:
    """Every object reachable from `root` through attributes and containers."""
    seen: dict[int, object] = {}
    stack = [root]
    while stack:
        obj = stack.pop()
        if id(obj) in seen or isinstance(obj, _LEAVES):
            continue
        seen[id(obj)] = obj
        if isinstance(obj, dict):
            stack.extend(obj.keys())
            stack.extend(obj.values())
        elif isinstance(obj, (list, tuple, set, frozenset)):
            stack.extend(obj)
        if hasattr(obj, "__dict__"):
            stack.extend(vars(obj).values())
        for slot in getattr(type(obj), "__slots__", ()):
            if hasattr(obj, slot):
                stack.append(getattr(obj, slot))
    return list(seen.values())


def test_no_attribute_path_reaches_a_frame(match_1: Played, whole: Run):
    # Invariant 1, by walking the object rather than trusting its docstring. The ingest it was
    # built from does hold frames, so the walk has something to find if the log keeps a path.
    assert any(isinstance(o, FrameWindow) for o in _reachable(whole.ingest))
    goal = _first_goal(match_1)
    reached = _reachable(_frozen(whole, _moment(goal.clock_ms, goal)))
    assert any(isinstance(o, Event) for o in reached)  # the walk got into the log
    assert not [type(o).__name__ for o in reached if isinstance(o, _BANNED)]
