"""Build `matchlens/understanding/signal_priors.json`, offline (R1).

    uv run python -m scripts.build_priors

Simulates the sample, measures every v1 signal every match minute, and writes one prior per
signal with the sample it came from. It also builds the same priors from twice the sample and
records how far each mean moved, which is the evidence that the lite sample is enough.

Not part of the pipeline: its output is data, committed beside the code that reads it.
"""

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from matchlens.ingest import Ingest
from matchlens.source import GENERATOR_VERSION, simulate
from matchlens.source.archetypes import ARCHETYPES
from matchlens.understanding.epochs import detect
from matchlens.understanding.priors import PRIORS_PATH, summarise
from matchlens.understanding.signals import Measurement, cadence, measure

# An equal split across the four archetypes, so the prior describes the generator's range of
# matches rather than any one shape. Five seeds each is the lite cut's 20 matches.
SEEDS_PER_ARCHETYPE = 5
# The stability check doubles the sample and asks each mean to move by less than this many of
# the 20-match prior's standard deviations.
TOLERANCE_STDDEVS = 0.1


def sample(seeds_per_archetype: int) -> dict[str, list[int]]:
    return {a: list(range(1, seeds_per_archetype + 1)) for a in sorted(ARCHETYPES)}


def measurements(job: tuple[str, int]) -> list[Measurement]:
    archetype, seed = job
    ingest = Ingest()
    for item in simulate(seed, ARCHETYPES[archetype]):
        ingest.accept(item)
    reader = ingest.record()
    end = max(e.clock_ms for e in reader.events_between(0, 2**62))
    return [m for c, e in cadence(detect(reader), end) for m in measure(reader, e, c)]


def priors_for(chosen: dict[str, list[int]], workers: int = 8) -> list[dict]:
    jobs = [(a, s) for a, seeds in chosen.items() for s in seeds]
    with ProcessPoolExecutor(workers) as pool:
        rows = [m for ms in pool.map(measurements, jobs) for m in ms]
    return [p.model_dump(mode="json") for p in summarise(rows, GENERATOR_VERSION)]


def build(path: Path = PRIORS_PATH) -> None:
    lite = sample(SEEDS_PER_ARCHETYPE)
    double = sample(2 * SEEDS_PER_ARCHETYPE)
    priors, check = priors_for(lite), priors_for(double)
    shifts = {
        p["signal"]: abs(p["mean"] - q["mean"]) / p["stddev"]
        for p, q in zip(priors, check, strict=True)
    }
    document = {
        "generator_version": GENERATOR_VERSION,
        "sample": lite,
        "priors": priors,
        "stability": {
            "sample": double,
            "means": {q["signal"]: q["mean"] for q in check},
            "shift_in_stddevs": shifts,
            "tolerance_stddevs": TOLERANCE_STDDEVS,
        },
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    for signal, shift in shifts.items():
        print(f"{signal:20} mean moved {shift:.3f} stddevs on doubling the sample")


if __name__ == "__main__":
    build()
