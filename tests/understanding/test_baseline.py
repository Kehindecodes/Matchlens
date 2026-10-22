"""U4: baselines, the shrinkage blend, z_match, z_prior and trend, over seed 1 on the comeback.

The match tests judge against R1's committed priors; the hand-worked ones use a small prior of
their own so the numbers can be checked with a calculator.
"""

import pytest

from matchlens.config import settings
from matchlens.models import Epoch, EpochTrigger, Signal, SignalPrior, SignalReading, Trend
from matchlens.understanding import priors as signal_priors
from matchlens.understanding.baseline import (
    Reference,
    judge,
    read,
    reference,
    trend,
    weight,
    z_score,
)
from matchlens.understanding.epochs import detect
from matchlens.understanding.signals import Measurement, cadence, measure
from tests.source.helpers import Played
from tests.source.helpers import reader as match_reader

K = settings.baseline_k_minutes
MINUTE = 60_000


def _measurements(match: Played) -> tuple[list[Epoch], list[Measurement]]:
    reader = match_reader(match)
    epochs = detect(reader)
    clocks = cadence(epochs, match.end_clock_ms)
    return epochs, [m for clock, epoch in clocks for m in measure(reader, epoch, clock)]


@pytest.fixture(scope="module")
def priors() -> dict[Signal, SignalPrior]:
    return signal_priors.load()


@pytest.fixture(scope="module")
def match(played) -> tuple[list[Epoch], list[Measurement]]:
    return _measurements(played)


@pytest.fixture(scope="module")
def readings(match, priors) -> list[SignalReading]:
    epochs, measurements = match
    return read(measurements, epochs, priors)


def _prior(mean: float = 8.0, stddev: float = 2.0) -> SignalPrior:
    return SignalPrior(
        signal=Signal.PRESSING_INTENSITY,
        mean=mean,
        stddev=stddev,
        sample_size=100,
        generator_version="test",
    )


def _epoch(n: int, start_ms: int) -> Epoch:
    return Epoch(
        epoch_id=f"m-epoch{n}",
        match_id="m",
        start_clock_ms=start_ms,
        score_state={"home": n, "away": 0},
        player_counts={"home": 11, "away": 11},
        trigger=None if n == 0 else EpochTrigger.GOAL,
    )


def _measurement(epoch: Epoch, minute: int, value: float) -> Measurement:
    return Measurement(
        signal=Signal.PRESSING_INTENSITY,
        team="home",
        clock_ms=minute * MINUTE,
        epoch_id=epoch.epoch_id,
        window_ms=min(minute * MINUTE - epoch.start_clock_ms, settings.signal_window_ms),
        value=value,
        n=10,
        confidence=0.5,
    )


# --- the maths, on hand-worked numbers -------------------------------------------------------


def test_w_is_near_zero_at_minute_1_half_by_15_and_three_quarters_by_45():
    assert weight(0, K) == 0
    assert weight(1, K) < 0.1
    assert weight(15, K) >= 0.5
    assert weight(45, K) >= 0.75


def test_the_worked_example():
    ref = reference([9.0, 10.0, 11.0, 10.0], _prior(), K)
    assert ref.mean == pytest.approx(8.421, abs=1e-3)
    assert ref.spread == pytest.approx(1.751, abs=1e-3)
    assert z_score(14.0, ref.mean, ref.spread) == pytest.approx(3.186, abs=1e-3)
    assert z_score(14.0, 8.0, 2.0) == 3.0


def test_no_history_is_the_prior_exactly():
    assert reference([], _prior(), K) == Reference(8.0, 2.0)


def test_one_reading_of_history_is_fine():
    ref = reference([10.0], _prior(), K)
    assert ref.mean == pytest.approx(weight(1, K) * 10 + (1 - weight(1, K)) * 8)
    assert ref.spread == pytest.approx((1 - weight(1, K)) * 2)  # one reading has no stddev


def test_a_flat_history_never_divides_by_zero():
    ref = reference([10.0] * 10_000, _prior(), K)
    assert ref.spread >= 0.1 * 2.0


@pytest.mark.parametrize(
    ("recent", "expected"),
    [
        ([10.0, 11.0, 14.0], Trend.RISING),
        ([14.0, 11.0, 10.0], Trend.FALLING),
        ([10.0, 10.1, 10.0], Trend.STEADY),
        ([10.0, 14.0], Trend.STEADY),  # too few readings to call
        ([14.0], Trend.STEADY),
    ],
)
def test_trend_agrees_with_the_last_few_readings(recent, expected):
    assert trend(recent, spread=1.73) is expected


# --- the history, on hand-built epochs -------------------------------------------------------


def test_a_reading_is_not_part_of_its_own_baseline():
    epoch = _epoch(0, 0)
    reading = judge(_measurement(epoch, 4, 100.0), [10.0, 10.0, 10.0], _prior(), K)
    w = weight(3, K)
    assert reading.baseline == pytest.approx(w * 10 + (1 - w) * 8)


def test_a_baseline_never_averages_across_a_structural_break():
    first, second = _epoch(0, 0), _epoch(1, 30 * MINUTE)
    measurements = [_measurement(first, m, 5.0) for m in range(1, 31)]
    measurements += [_measurement(second, m, 20.0) for m in range(31, 61)]
    prior = _prior(mean=10.0)
    readings = read(measurements, [first, second], {Signal.PRESSING_INTENSITY: prior})
    after = [r for r in readings if r.epoch_id == second.epoch_id]
    k = settings.baseline_k_minutes_after_break
    for n, r in enumerate(after):
        w = weight(n, k)
        assert r.baseline == pytest.approx(w * 20 + (1 - w) * 10)


def test_a_break_uses_the_after_break_k(monkeypatch):
    monkeypatch.setattr(settings, "baseline_k_minutes_after_break", 5)
    first, second = _epoch(0, 0), _epoch(1, 30 * MINUTE)
    measurements = [_measurement(first, 10, 5.0), _measurement(first, 11, 5.0)]
    measurements += [_measurement(second, 31, 20.0), _measurement(second, 32, 20.0)]
    readings = read(measurements, [first, second], {Signal.PRESSING_INTENSITY: _prior(10.0)})
    assert readings[1].baseline == pytest.approx(weight(1, K) * 5 + (1 - weight(1, K)) * 10)
    assert readings[3].baseline == pytest.approx(weight(1, 5) * 20 + (1 - weight(1, 5)) * 10)


def test_a_placeholder_is_judged_but_kept_out_of_the_history():
    epoch = _epoch(0, 0)
    empty = Measurement(**{**vars(_measurement(epoch, 2, 0.0)), "n": 0})
    measurements = [_measurement(epoch, 1, 10.0), empty, _measurement(epoch, 3, 10.0)]
    readings = read(measurements, [epoch], {Signal.PRESSING_INTENSITY: _prior()})
    assert len(readings) == 3
    w = weight(1, K)  # minute 3 sees only minute 1: the placeholder never joined the history
    assert readings[2].baseline == pytest.approx(w * 10 + (1 - w) * 8)


def test_an_empty_chance_quality_window_is_a_real_zero():
    epoch = _epoch(0, 0)
    prior = _prior()
    chance = [
        Measurement(
            **{**vars(_measurement(epoch, minute, 0.0)), "signal": Signal.CHANCE_QUALITY, "n": 0}
        )
        for minute in (1, 2, 3)
    ]
    readings = read(chance, [epoch], {Signal.CHANCE_QUALITY: prior})
    w = weight(2, K)  # minute 3 sees both earlier zeros
    assert readings[2].baseline == pytest.approx(w * 0 + (1 - w) * 8)


def test_readings_are_judged_in_clock_order_whatever_order_they_arrive_in():
    epoch = _epoch(0, 0)
    measurements = [_measurement(epoch, m, float(m)) for m in range(1, 11)]
    prior = {Signal.PRESSING_INTENSITY: _prior()}
    assert read(list(reversed(measurements)), [epoch], prior) == read(measurements, [epoch], prior)


# --- the acceptance criteria, over seed 1 on the comeback ------------------------------------


def test_no_z_score_flood_in_the_opening_minutes(readings):
    opening = [r for r in readings if r.clock_ms <= 10 * MINUTE]
    assert opening
    assert all(abs(r.z_match) < 3 for r in opening)


def test_after_a_goal_the_baseline_restarts_from_the_prior(readings, match, priors):
    epochs, _ = match
    goal = next(e for e in epochs if e.trigger is EpochTrigger.GOAL)
    after = [r for r in readings if r.epoch_id == goal.epoch_id]
    first_clock = min(r.clock_ms for r in after)
    for r in (r for r in after if r.clock_ms == first_clock):
        assert r.baseline == priors[r.signal].mean  # w = 0: no history in the new epoch
        assert r.z_match == pytest.approx(r.z_prior)
        assert r.window_ms < settings.signal_window_ms


def test_the_reading_after_a_goal_has_lower_confidence(readings, match):
    epochs, _ = match
    goal = next(e for e in epochs if e.trigger is EpochTrigger.GOAL)
    first_after = min(r.clock_ms for r in readings if r.epoch_id == goal.epoch_id)
    before = {
        (r.signal, r.team): r.confidence for r in readings if r.clock_ms == first_after - MINUTE
    }
    after = {(r.signal, r.team): r.confidence for r in readings if r.clock_ms == first_after}
    assert sum(after.values()) < sum(before.values())


def test_every_reading_carries_the_epoch_containing_its_clock(readings, match):
    epochs, _ = match
    for r in readings:
        containing = [e for e in epochs if e.start_clock_ms < r.clock_ms][-1]
        assert r.epoch_id == containing.epoch_id


def test_one_reading_per_measurement_with_unique_ids(readings, match):
    _, measurements = match
    assert len(readings) == len(measurements)
    assert len({r.reading_id for r in readings}) == len(readings)


def test_the_same_match_gives_the_same_readings(readings, match, priors):
    epochs, measurements = match
    assert read(measurements, epochs, priors) == readings
