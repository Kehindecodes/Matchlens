"""M1a: readings on the live path, over seed 1 on the comeback.

The criterion that matters is the first one: streaming a match through `Understanding.observe`
gives exactly the readings the batch path gives over the finished log. Everything else here
checks something the batch path cannot show, which is what the streaming form does between calls.
"""

from functools import partial

import pytest

from apps.pipeline import Pipeline
from matchlens import calltrace
from matchlens.config import settings
from matchlens.ingest import Ingest
from matchlens.models import Event, Frame, Signal, SignalPrior, SignalReading
from matchlens.source import StreamItem, simulate
from matchlens.source.archetypes import ARCHETYPES
from matchlens.understanding import Understanding
from matchlens.understanding import priors as signal_priors
from matchlens.understanding.baseline import read, z_score
from matchlens.understanding.epochs import detect
from matchlens.understanding.priors import StalePrior
from matchlens.understanding.signals import SIGNALS, cadence, measure
from tests.source.helpers import reader as match_reader


@pytest.fixture(scope="module")
def priors() -> dict[Signal, SignalPrior]:
    return signal_priors.load()


def _stream(
    items: list[StreamItem], priors: dict[Signal, SignalPrior]
) -> list[tuple[StreamItem, list[SignalReading]]]:
    """Each item as Ingest then Understanding see it, with the readings it completed."""
    ingest = Ingest()
    understanding = Understanding(ingest.record, priors)
    emitted = []
    for item in items:
        ingest.accept(item)
        emitted.append((item, understanding.observe(item)))
    return emitted


def _readings(items: list[StreamItem], priors: dict[Signal, SignalPrior]) -> list[SignalReading]:
    return [r for _, readings in _stream(items, priors) for r in readings]


@pytest.fixture(scope="module")
def streamed(played, priors) -> list[tuple[StreamItem, list[SignalReading]]]:
    return _stream(played.items, priors)


@pytest.fixture(scope="module")
def live(streamed) -> list[SignalReading]:
    return [r for _, readings in streamed for r in readings]


@pytest.fixture(scope="module")
def epochs(played):
    return detect(match_reader(played))


# --- batch and streaming agree -----------------------------------------------------------------


def test_streaming_a_match_gives_the_readings_the_batch_path_gives(played, priors, epochs, live):
    reader = match_reader(played)
    measurements = [
        m
        for clock, epoch in cadence(epochs, played.end_clock_ms)
        for m in measure(reader, epoch, clock)
    ]
    assert live == read(measurements, epochs, priors)


def test_every_cadence_clock_has_a_reading_for_both_teams_and_all_four_signals(
    played, epochs, live
):
    clocks = [clock for clock, _ in cadence(epochs, played.end_clock_ms)]
    teams = [t.team_id for t in played.setup.match.teams]
    expected = {(c, team, s) for c in clocks for team in teams for s in SIGNALS}
    assert len(SIGNALS) == 4
    assert [(r.clock_ms, r.team, r.signal) for r in live] != []
    assert {(r.clock_ms, r.team, r.signal) for r in live} == expected
    assert len(live) == len(expected)  # none twice


def test_a_reading_is_emitted_only_once_the_clock_has_passed_it(streamed):
    for item, readings in streamed:
        assert all(r.clock_ms < item.clock_ms for r in readings)


def test_a_reading_is_emitted_by_the_first_event_after_its_clock(streamed):
    # Late is allowed (delivery delays), but not later than the next event: that is the whole
    # point of noticing the boundary as the clock crosses it.
    previous_clock = 0
    for item, readings in streamed:
        if not isinstance(item, Event):
            continue
        for r in readings:
            assert previous_clock <= r.clock_ms < item.clock_ms
        previous_clock = item.clock_ms


def test_events_at_the_reading_clock_all_count_though_they_arrive_one_by_one(played, priors):
    # Two events land exactly on a cadence clock. The reading there counts both, so it cannot
    # be taken when the first arrives, only when something later does.
    boundary_ms = 10 * settings.signal_cadence_ms
    events = [i for i in played.items if isinstance(i, Event) and i.clock_ms < boundary_ms + 60_000]
    first = next(n for n, e in enumerate(events) if e.clock_ms >= boundary_ms)
    retimed = [
        e.model_copy(update={"clock_ms": boundary_ms}) if first <= n <= first + 1 else e
        for n, e in enumerate(events)
    ]
    items = [played.setup, *retimed]
    ingest = Ingest()
    for item in items:
        ingest.accept(item)
    reader = ingest.record()
    epochs = detect(reader)
    measurements = [m for c, e in cadence(epochs, boundary_ms) for m in measure(reader, e, c)]
    expected = [r for r in read(measurements, epochs, priors) if r.clock_ms == boundary_ms]
    streamed = [r for r in _readings(items, priors) if r.clock_ms == boundary_ms]
    assert streamed == expected
    assert len(streamed) == 2 * len(SIGNALS)


# --- the reset at an epoch boundary ------------------------------------------------------------


def _first_in_each_epoch(live: list[SignalReading]) -> list[SignalReading]:
    seen = set()
    firsts = []
    for r in live:
        key = (r.epoch_id, r.signal, r.team)
        if key not in seen:
            seen.add(key)
            firsts.append(r)
    return firsts


def test_the_window_restarts_at_every_epoch_boundary(epochs, live):
    start = {e.epoch_id: e.start_clock_ms for e in epochs}
    for r in live:
        assert r.window_ms == min(r.clock_ms - start[r.epoch_id], settings.signal_window_ms)
    after_a_break = [r for r in live if r.epoch_id != epochs[0].epoch_id and r.window_ms < 60_001]
    assert after_a_break, "no reading fell within a minute of a break"


def test_history_does_not_carry_across_a_boundary(epochs, priors, live):
    # An empty history is the prior itself, so a first reading in a new epoch sitting anywhere
    # else has averaged in the epoch before it.
    new_epochs = {e.epoch_id for e in epochs[1:]}
    firsts = [r for r in _first_in_each_epoch(live) if r.epoch_id in new_epochs]
    assert len(firsts) == len(new_epochs) * 2 * len(SIGNALS)
    for r in firsts:
        assert r.baseline == priors[r.signal].mean, (r.epoch_id, r.signal, r.team)


def test_a_reading_straight_after_a_break_is_judged_against_the_prior_alone(epochs, priors, live):
    new_epochs = {e.epoch_id for e in epochs[1:]}
    for r in _first_in_each_epoch(live):
        if r.epoch_id in new_epochs:
            prior = priors[r.signal]
            assert r.z_match == r.z_prior == z_score(r.value, prior.mean, prior.stddev)


def test_confidence_is_lower_straight_after_a_break_than_in_a_full_window(epochs, live):
    new_epochs = {e.epoch_id for e in epochs[1:]}
    after = [r.confidence for r in _first_in_each_epoch(live) if r.epoch_id in new_epochs]
    full = [r.confidence for r in live if r.window_ms == settings.signal_window_ms]
    assert sum(after) / len(after) < sum(full) / len(full)


# --- frames ------------------------------------------------------------------------------------


def test_no_frame_changes_a_reading(played, priors, streamed):
    # A prefix is enough: frames are everywhere in the stream, so any influence shows early.
    cutoff_ms = 20 * settings.signal_cadence_ms
    last_event = max(
        n for n, i in enumerate(played.items) if isinstance(i, Event) and i.clock_ms <= cutoff_ms
    )
    prefix = played.items[: last_event + 1]
    without_frames = [i for i in prefix if not isinstance(i, Frame)]
    assert len(without_frames) < len(prefix)
    with_frames = [r for _, readings in streamed[: last_event + 1] for r in readings]
    assert len(with_frames) > 0
    assert _readings(without_frames, priors) == with_frames


def test_observing_a_frame_or_the_roster_emits_nothing(played, priors):
    ingest = Ingest()
    understanding = Understanding(ingest.record, priors)
    ingest.accept(played.setup)
    assert understanding.observe(played.setup) == []
    frame = next(i for i in played.items if isinstance(i, Frame))
    ingest.accept(frame)
    assert understanding.observe(frame) == []


# --- determinism and state ---------------------------------------------------------------------


def test_the_same_seed_gives_the_same_readings_in_the_same_order(priors, live):
    again = list(simulate(1, ARCHETYPES["comeback"]))
    assert _readings(again, priors) == live


def test_two_understandings_share_no_state(played, priors, live):
    first_ingest, second_ingest = Ingest(), Ingest()
    first = Understanding(first_ingest.record, priors)
    second = Understanding(second_ingest.record, priors)
    out_first, out_second = [], []
    for item in played.items:
        first_ingest.accept(item)
        out_first += first.observe(item)
    for item in played.items:
        second_ingest.accept(item)
        out_second += second.observe(item)
    assert out_first == out_second == live


def test_observing_enters_understanding(played, priors):
    ingest = Ingest()
    understanding = Understanding(ingest.record, priors)
    event = next(i for i in played.items if isinstance(i, Event))
    frame = next(i for i in played.items if isinstance(i, Frame))
    for item in (played.setup, frame, event):
        ingest.accept(item)
        with calltrace.recording() as entered:
            understanding.observe(item)
        assert "Understanding" in entered


# --- priors at startup -------------------------------------------------------------------------


@pytest.fixture
def stale_priors(tmp_path, monkeypatch) -> None:
    """Priors on disk built by another generator, and `priors.load()` pointed at them."""
    text = signal_priors.PRIORS_PATH.read_text().replace(
        signal_priors.load()[Signal.TERRITORY].generator_version, "not-this-generator"
    )
    path = tmp_path / "signal_priors.json"
    path.write_text(text)
    monkeypatch.setattr(signal_priors, "load", partial(signal_priors.load, path))


@pytest.mark.usefixtures("stale_priors")
def test_a_stale_prior_stops_understanding_from_starting():
    with pytest.raises(StalePrior):
        Understanding(Ingest().record)


@pytest.mark.usefixtures("stale_priors")
def test_a_stale_prior_stops_the_pipeline_from_starting():
    with pytest.raises(StalePrior):
        Pipeline()


def test_the_pipeline_starts_on_the_committed_priors():
    Pipeline()


def test_an_event_at_a_break_belongs_to_the_epoch_before_it(played, priors, epochs):
    ingest = Ingest()
    understanding = Understanding(ingest.record, priors)
    for item in played.items:
        ingest.accept(item)
        understanding.observe(item)
    for before, after in zip(epochs, epochs[1:], strict=False):
        assert understanding.epoch_at(after.start_clock_ms) == before
        assert understanding.epoch_at(after.start_clock_ms + 1) == after
