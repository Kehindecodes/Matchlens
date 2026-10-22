"""Baselines, z-scores and trend: what turns a U3 `Measurement` into a `SignalReading` (U4).

A reading is judged against the readings before it in the same epoch, for the same signal and
team. The baseline blends that history's mean with the offline prior, trusting the history by
`w = n / (n + k)`, where `n` counts those earlier readings (D11). D15 means a new epoch starts with
no history, so after a goal, a red card or half time `w` is back to zero and the baseline is the
prior again, exactly as at kickoff (D26). The spread blends the same way.

A reading is never part of its own baseline, and nothing reads past it: each reading is judged,
then appended to the history the next one is judged against.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from matchlens import calltrace
from matchlens.config import settings
from matchlens.models import Epoch, Signal, SignalPrior, SignalReading, Trend
from matchlens.understanding.signals import Measurement

SPREAD_FLOOR = 0.1  # of the prior's stddev, so a flat stretch can never divide by zero
TREND_READINGS = 3  # the trend compares the newest reading with the one this many back
TREND_DEAD_BAND = 0.25  # of the spread: a smaller change than this is steady


@dataclass(frozen=True)
class Reference:
    """What counts as normal for one reading: the blended mean and spread."""

    mean: float
    spread: float


def weight(n: int, k: float) -> float:
    """The trust in this match's own history: 0 with none, one half at `k` readings, towards 1."""
    return n / (n + k)


def reference(history: Sequence[float], prior: SignalPrior, k: float) -> Reference:
    """The history's mean and stddev, each blended with the prior by `weight`."""
    if not history:
        return Reference(prior.mean, prior.stddev)
    w = weight(len(history), k)
    values = np.asarray(history, dtype=float)
    mean = w * float(values.mean()) + (1 - w) * prior.mean
    spread = w * float(values.std()) + (1 - w) * prior.stddev
    return Reference(mean, max(spread, SPREAD_FLOOR * prior.stddev))


def z(value: float, mean: float, spread: float) -> float:
    """How many spreads `value` sits from `mean`."""
    return (value - mean) / spread


def trend(recent: Sequence[float], spread: float) -> Trend:
    """Rising, falling or steady over the last `TREND_READINGS` values, newest last."""
    if len(recent) < TREND_READINGS:
        return Trend.STEADY
    change = recent[-1] - recent[-TREND_READINGS]
    band = TREND_DEAD_BAND * spread
    if change > band:
        return Trend.RISING
    if change < -band:
        return Trend.FALLING
    return Trend.STEADY


def judge(
    measurement: Measurement, history: Sequence[float], prior: SignalPrior, k: float
) -> SignalReading:
    """One measurement as a reading, against the earlier values in its epoch."""
    ref = reference(history, prior, k)
    m = measurement
    return SignalReading(
        reading_id=f"{m.epoch_id}-{m.signal}-{m.team}-{m.clock_ms}",
        signal=m.signal,
        team=m.team,
        clock_ms=m.clock_ms,
        window_ms=m.window_ms,
        value=m.value,
        baseline=ref.mean,
        z_match=z(m.value, ref.mean, ref.spread),
        z_prior=z(m.value, prior.mean, prior.stddev),
        trend=trend([*history[-(TREND_READINGS - 1) :], m.value], ref.spread),
        confidence=m.confidence,
        epoch_id=m.epoch_id,
    )


def read(
    measurements: Iterable[Measurement],
    epochs: Sequence[Epoch],
    priors: Mapping[Signal, SignalPrior],
) -> list[SignalReading]:
    """Every measurement as a reading, in clock order, each judged only on what came before it."""
    calltrace.entered("Understanding")
    k = {
        e.epoch_id: settings.baseline_k_minutes
        if e.trigger is None
        else settings.baseline_k_minutes_after_break
        for e in epochs
    }
    histories: dict[tuple[str, Signal, str], list[float]] = defaultdict(list)
    readings = []
    for m in sorted(measurements, key=lambda m: m.clock_ms):
        history = histories[(m.epoch_id, m.signal, m.team)]
        readings.append(judge(m, history, priors[m.signal], k[m.epoch_id]))
        history.append(m.value)
    return readings
