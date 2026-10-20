"""U3: the four v1 signals over seed 1, on the comeback and on the one-sided match (R2)."""

import ast
import inspect
import statistics
from collections import defaultdict

import pytest

from matchlens.config import settings
from matchlens.ingest import Ingest, RecordReader
from matchlens.ingest.events import InMemoryEventRepository
from matchlens.models import Event, Outcome, Signal
from matchlens.source import simulate
from matchlens.understanding import signals
from matchlens.understanding.epochs import detect
from matchlens.understanding.signals import (
    SIGNALS,
    Interval,
    Measurement,
    SignalWindow,
    cadence,
    confidence,
    measure,
    window_at,
)
from tests.source.helpers import Played, split
from tests.source.helpers import played as simulated
from tests.source.helpers import reader as match_reader


@pytest.fixture(scope="module")
def reader(played) -> RecordReader:
    ingest = Ingest()
    for item in played.items:
        ingest.accept(item)
    return ingest.record()


@pytest.fixture(scope="module")
def epochs(reader):
    return detect(reader)


@pytest.fixture(scope="module")
def readings(reader, epochs, played) -> list[Measurement]:
    return [m for c, e in cadence(epochs, played.end_clock_ms) for m in measure(reader, e, c)]


def _series(readings: list[Measurement], signal: Signal, team: str) -> list[Measurement]:
    return [m for m in readings if m.signal is signal and m.team == team]


def _log(played: Played, events: list[Event]) -> RecordReader:
    repository = InMemoryEventRepository()
    for event in events:
        repository.append(event)
    return RecordReader(played.setup, repository)


def test_one_function_per_v1_signal_with_one_signature_and_documented_units():
    assert set(SIGNALS) == set(Signal) - {Signal.LINE_HEIGHT}
    shapes = {str(inspect.signature(fn)) for fn in SIGNALS.values()}
    assert len(shapes) == 1
    assert all(fn.__doc__ and "`n`" in fn.__doc__ for fn in SIGNALS.values())


def test_no_signal_reads_a_frame():
    tree = ast.parse(inspect.getsource(signals))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not {"Frame", "FrameAccess", "frame_window", "frame_access"} & names


def test_the_window_leaves_out_its_start_and_counts_its_end(played, reader):
    a, b = played.events[200], played.events[260]
    held = [e.event_id for e in Interval(a.clock_ms, b.clock_ms).events(reader)]
    assert a.event_id not in held and b.event_id in held
    assert held == [e.event_id for e in played.events if a.clock_ms < e.clock_ms <= b.clock_ms]


def test_stopped_time_adds_nothing(played, reader):
    """Cut the stoppage out of the log: the same events give the same values."""
    events = played.events
    out = next(i for i, e in enumerate(events) if e.outcome is Outcome.OUT_OF_PLAY and i > 300)
    gap = events[out + 1].clock_ms - events[out].clock_ms
    assert gap > 10_000  # a real stoppage, waiting for the restart
    start, end = events[out].clock_ms - 120_000, events[out].clock_ms + 120_000
    squeezed = [
        e if i <= out else e.model_copy(update={"clock_ms": e.clock_ms - gap})
        for i, e in enumerate(events)
    ]
    full = SignalWindow.read(reader, Interval(start, end))
    in_play = SignalWindow.read(_log(played, squeezed), Interval(start, end - gap))
    for team in (t.team_id for t in played.setup.match.teams):
        for fn in SIGNALS.values():
            assert fn(full, team) == fn(in_play, team), fn.__name__


def test_confidence_is_much_lower_on_a_thin_window(reader, epochs):
    goal = next(e for e in epochs if e.trigger is not None and e.trigger.value == "goal")
    thin = measure(reader, goal, goal.start_clock_ms + 8_000)
    full = measure(reader, goal, goal.start_clock_ms + settings.signal_window_ms)
    assert max(m.n for m in thin) <= 2
    for a, b in zip(thin, full, strict=True):
        assert a.confidence <= b.confidence
    assert max(m.confidence for m in thin) < min(m.confidence for m in full if m.n > 8)
    assert confidence(2) < confidence(30) / 2


def test_the_clamped_width_comes_back_with_the_value(reader, epochs):
    goal = next(e for e in epochs if e.trigger is not None)
    young = measure(reader, goal, goal.start_clock_ms + 90_000)
    old = measure(reader, goal, goal.start_clock_ms + settings.signal_window_ms + 90_000)
    assert {m.window_ms for m in young} == {90_000}
    assert {m.window_ms for m in old} == {settings.signal_window_ms}
    assert window_at(goal.start_clock_ms + 90_000, goal).start_ms == goal.start_clock_ms


def test_every_reading_sits_inside_one_epoch(readings, epochs):
    starts = {e.epoch_id: e.start_clock_ms for e in epochs}
    for m in readings:
        assert m.clock_ms - m.window_ms >= starts[m.epoch_id]
        assert m.clock_ms % settings.signal_cadence_ms == 0


def test_the_same_seed_gives_the_same_readings(readings, played):
    again = split(list(simulate(1)))
    ingest = Ingest()
    for item in again.items:
        ingest.accept(item)
    r = ingest.record()
    e = detect(r)
    assert [m for c, ep in cadence(e, again.end_clock_ms) for m in measure(r, ep, c)] == readings


def test_the_signals_read_sensibly_on_the_comeback(readings, played):
    """Shares split between the teams, and home's second-half surge shows in all four."""
    home, away = (t.team_id for t in played.setup.match.teams)
    for signal in (Signal.TERRITORY, Signal.POSSESSION_CONTROL):
        for h, a in zip(
            _series(readings, signal, home), _series(readings, signal, away), strict=True
        ):
            assert h.value + a.value == pytest.approx(1.0)
    assert all(m.value >= 0 for m in readings)

    half_time = 47 * 60_000

    def mean(signal: Signal, team: str, second: bool) -> float:
        rows = [
            m.value for m in _series(readings, signal, team) if (m.clock_ms > half_time) == second
        ]
        return statistics.mean(rows)

    assert mean(Signal.TERRITORY, home, True) > mean(Signal.TERRITORY, home, False)
    assert mean(Signal.POSSESSION_CONTROL, home, True) > mean(
        Signal.POSSESSION_CONTROL, home, False
    )
    assert mean(Signal.CHANCE_QUALITY, home, True) > mean(Signal.CHANCE_QUALITY, home, False)
    assert mean(Signal.PRESSING_INTENSITY, home, True) < mean(
        Signal.PRESSING_INTENSITY, home, False
    )


def test_the_signals_read_sensibly_on_the_one_sided_match():
    """The second archetype: home on top from first to last, and all four signals agree."""
    match = simulated("one_sided", 1)
    r = match_reader(match)
    rows = [m for c, e in cadence(detect(r), match.end_clock_ms) for m in measure(r, e, c)]
    home, away = (t.team_id for t in match.setup.match.teams)

    def mean(signal: Signal, team: str) -> float:
        return statistics.mean(m.value for m in _series(rows, signal, team))

    assert mean(Signal.TERRITORY, home) > 0.6
    assert mean(Signal.POSSESSION_CONTROL, home) > 0.55
    assert mean(Signal.CHANCE_QUALITY, home) > 2 * mean(Signal.CHANCE_QUALITY, away)
    for signal in (Signal.TERRITORY, Signal.POSSESSION_CONTROL):
        for h, a in zip(_series(rows, signal, home), _series(rows, signal, away), strict=True):
            assert h.value + a.value == pytest.approx(1.0)


def test_pressing_moves_apart_from_possession_on_the_comeback(readings, played):
    """D10's orthogonal basis: a side can press hard without having the ball."""
    for team in (t.team_id for t in played.setup.match.teams):
        control = _series(readings, Signal.POSSESSION_CONTROL, team)
        press = _series(readings, Signal.PRESSING_INTENSITY, team)
        r = statistics.correlation([m.value for m in control], [m.value for m in press])
        assert abs(r) < 0.6, f"{team}: r = {r:.2f}"
        hard = statistics.median(m.value for m in press)
        apart = [c for c, p in zip(control, press, strict=True) if c.value < 0.5 and p.value < hard]
        assert apart, f"{team} never pressed hard while having less of the ball"


def test_readings_per_minute_cover_both_teams_and_all_four_signals(readings):
    per_clock: dict[int, set] = defaultdict(set)
    for m in readings:
        per_clock[m.clock_ms].add((m.signal, m.team))
    assert {len(v) for v in per_clock.values()} == {8}
