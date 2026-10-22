"""Signal priors: the offline reference each signal blends towards on a cold start (R1, D11).

`summarise` turns a sample of measurements into one `SignalPrior` per v1 signal, and `load` reads
the committed file back, refusing it loudly if a different generator made it. Choosing the sample
(which archetypes, which seeds) is `scripts/build_priors.py`'s job, because nothing here may know
about archetypes (D25).

A measurement that saw nothing and holds a placeholder is left out of the sample. Chance quality's
empty windows are kept: "no shots" is a real 0 (D28).
"""

import json
import statistics
from collections.abc import Iterable
from pathlib import Path

from matchlens.models import Signal, SignalPrior
from matchlens.source import GENERATOR_VERSION
from matchlens.understanding.signals import SIGNALS, Measurement, is_placeholder

PRIORS_PATH = Path(__file__).with_name("signal_priors.json")


class StalePrior(RuntimeError):
    """The priors on disk were made by a different generator than the one running."""


def summarise(measurements: Iterable[Measurement], generator_version: str) -> list[SignalPrior]:
    """Mean and sample standard deviation of every v1 signal's values, one row per signal."""
    values: dict[Signal, list[float]] = {signal: [] for signal in SIGNALS}
    for m in measurements:
        if not is_placeholder(m):
            values[m.signal].append(m.value)
    return [
        SignalPrior(
            signal=signal,
            mean=statistics.fmean(vs),
            stddev=statistics.stdev(vs),
            sample_size=len(vs),
            generator_version=generator_version,
        )
        for signal, vs in values.items()
    ]


def load(
    path: Path = PRIORS_PATH, generator_version: str = GENERATOR_VERSION
) -> dict[Signal, SignalPrior]:
    """The committed priors, by signal. Raises `StalePrior` if they belong to another generator."""
    priors = [SignalPrior.model_validate(row) for row in json.loads(path.read_text())["priors"]]
    stale = sorted({p.generator_version for p in priors} - {generator_version})
    if stale:
        raise StalePrior(
            f"{path.name} was built by {', '.join(stale)}, but the generator is "
            f"{generator_version}. Rebuild it: uv run python -m scripts.build_priors"
        )
    return {p.signal: p for p in priors}
