"""Baselines, z-scores and trend: what turns a U3 `Measurement` into a `SignalReading` (U4).

A reading is judged against the readings before it in the same epoch, for the same signal and
team. The baseline blends that history's mean with the offline prior, trusting the history by
`w = n / (n + k)`, where `n` counts those earlier readings (D11). D15 means a new epoch starts with
no history, so after a goal, a red card or half time `w` is back to zero and the baseline is the
prior again, exactly as at kickoff (D26). The spread blends the same way.

A reading is never part of its own baseline, and nothing reads past it: each reading is judged,
then appended to the history the next one is judged against.
"""

import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from matchlens import calltrace
from matchlens.config import settings
from matchlens.models import Epoch, Signal, SignalPrior, SignalReading, Trend
from matchlens.understanding.signals import Measurement

SPREAD_FLOOR = 0.1
TREND_READINGS = 3
TREND_DEAD_BAND = 0.25


@dataclass(frozen=True)
class Reference:
    """What counts as normal for one reading: the blended mean and spread."""

    mean: float
    spread: float


def weight(readings_so_far: int, half_trust_readings: float) -> float:
    """The trust in this match's own history: 0 with none, one half at `half_trust_readings`."""
    return readings_so_far / (readings_so_far + half_trust_readings)


def reference(
    history: Sequence[float], prior: SignalPrior, half_trust_readings: float
) -> Reference:
    """The history's mean and stddev, each blended with the prior by `weight`.

    The stddev is the sample one, as R1's priors use, so the two spreads are comparable. A single
    reading has none, so it contributes nothing and the floor stands in.
    """
    if not history:
        return Reference(prior.mean, prior.stddev)
    match_weight = weight(len(history), half_trust_readings)
    prior_weight = 1 - match_weight
    match_stddev = statistics.stdev(history) if len(history) > 1 else 0.0
    mean = match_weight * statistics.fmean(history) + prior_weight * prior.mean
    spread = match_weight * match_stddev + prior_weight * prior.stddev
    return Reference(mean, max(spread, SPREAD_FLOOR * prior.stddev))


def z_score(value: float, mean: float, spread: float) -> float:
    """How many spreads `value` sits from `mean`."""
    return (value - mean) / spread


def trend(recent: Sequence[float], spread: float) -> Trend:
    """Rising, falling or steady over the last `TREND_READINGS` values, newest last."""
    if len(recent) < TREND_READINGS:
        return Trend.STEADY
    change = recent[-1] - recent[-TREND_READINGS]
    dead_band = TREND_DEAD_BAND * spread
    if change > dead_band:
        return Trend.RISING
    if change < -dead_band:
        return Trend.FALLING
    return Trend.STEADY


def judge(
    measurement: Measurement,
    history: Sequence[float],
    prior: SignalPrior,
    half_trust_readings: float,
) -> SignalReading:
    """One measurement as a reading, against the earlier values in its epoch."""
    normal = reference(history, prior, half_trust_readings)
    recent = [*history[-(TREND_READINGS - 1) :], measurement.value]
    return SignalReading(
        reading_id=(
            f"{measurement.epoch_id}-{measurement.signal}-{measurement.team}-{measurement.clock_ms}"
        ),
        signal=measurement.signal,
        team=measurement.team,
        clock_ms=measurement.clock_ms,
        window_ms=measurement.window_ms,
        value=measurement.value,
        baseline=normal.mean,
        z_match=z_score(measurement.value, normal.mean, normal.spread),
        z_prior=z_score(measurement.value, prior.mean, prior.stddev),
        trend=trend(recent, normal.spread),
        confidence=measurement.confidence,
        epoch_id=measurement.epoch_id,
    )


def read(
    measurements: Iterable[Measurement],
    epochs: Sequence[Epoch],
    priors: Mapping[Signal, SignalPrior],
) -> list[SignalReading]:
    """Every measurement as a reading, in clock order, each judged only on what came before it."""
    calltrace.entered("Understanding")
    half_trust_by_epoch = {
        epoch.epoch_id: settings.baseline_k_minutes
        if epoch.trigger is None
        else settings.baseline_k_minutes_after_break
        for epoch in epochs
    }
    histories: dict[tuple[str, Signal, str], list[float]] = defaultdict(list)
    readings = []
    for measurement in sorted(measurements, key=lambda measurement: measurement.clock_ms):
        history = histories[(measurement.epoch_id, measurement.signal, measurement.team)]
        prior = priors[measurement.signal]
        half_trust_readings = half_trust_by_epoch[measurement.epoch_id]
        readings.append(judge(measurement, history, prior, half_trust_readings))
        history.append(measurement.value)
    return readings
