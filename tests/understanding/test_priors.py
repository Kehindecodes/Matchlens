"""R1: the committed signal priors, the loader that guards them, and the sample behind them."""

import hashlib
import json

import pytest

from matchlens.models import Signal
from matchlens.source import GENERATOR_VERSION
from matchlens.source.archetypes import ARCHETYPES
from matchlens.understanding.epochs import detect
from matchlens.understanding.priors import PRIORS_PATH, StalePrior, load, summarise
from matchlens.understanding.signals import SIGNALS, cadence, is_placeholder, measure
from scripts.build_priors import SEEDS_PER_ARCHETYPE, priors_for, sample
from tests.source.helpers import played, reader

DOCUMENT = json.loads(PRIORS_PATH.read_text())
# What `GENERATOR_VERSION` currently generates, seed 1 of each archetype. If one of these moves,
# the generator changed: bump the version, update the digests and rebuild the priors.
DIGESTS = {
    "comeback": "828b8ea241c7d585",
    "one_sided": "df34284309ef545c",
    "scrappy": "681a4915fbc3988e",
    "tight": "c16cac92f71ce54c",
}


def _digest(archetype: str) -> str:
    h = hashlib.sha256()
    for item in played(archetype, 1).items:
        h.update(item.model_dump_json().encode())
    return h.hexdigest()[:16]


def test_one_prior_per_v1_signal_and_none_for_line_height():
    priors = load()
    assert set(priors) == set(SIGNALS)
    assert Signal.LINE_HEIGHT not in priors


def test_every_prior_carries_its_sample_size_and_generator():
    for prior in load().values():
        assert prior.sample_size > 0
        assert prior.generator_version == GENERATOR_VERSION


def test_the_sample_spans_all_four_archetypes_equally():
    chosen = DOCUMENT["sample"]
    assert set(chosen) == set(ARCHETYPES) and len(chosen) == 4
    assert {len(seeds) for seeds in chosen.values()} == {SEEDS_PER_ARCHETYPE}
    assert chosen == sample(SEEDS_PER_ARCHETYPE)


def test_every_signal_varies():
    assert all(p.stddev > 0 for p in load().values())


def test_a_prior_from_another_generator_is_refused(tmp_path):
    stale = json.loads(PRIORS_PATH.read_text())
    for row in stale["priors"]:
        row["generator_version"] = "generator-0"
    path = tmp_path / "signal_priors.json"
    path.write_text(json.dumps(stale))
    with pytest.raises(StalePrior, match="generator-0.*" + GENERATOR_VERSION):
        load(path)


def test_the_running_generator_is_the_one_the_priors_were_built_for():
    """Loading under any other version fails, so a stale prior cannot be used quietly."""
    assert load(generator_version=GENERATOR_VERSION)
    with pytest.raises(StalePrior):
        load(generator_version="generator-1")


def test_doubling_the_sample_moves_no_mean_beyond_the_tolerance():
    """The evidence that 20 matches is enough, recorded when the priors were built."""
    stability = DOCUMENT["stability"]
    assert {len(s) for s in stability["sample"].values()} == {2 * SEEDS_PER_ARCHETYPE}
    tolerance = stability["tolerance_stddevs"]
    assert all(shift < tolerance for shift in stability["shift_in_stddevs"].values())


def test_summarising_the_same_measurements_twice_gives_identical_priors():
    match = played("comeback", 1)
    r = reader(match)
    rows = [m for c, e in cadence(detect(r), match.end_clock_ms) for m in measure(r, e, c)]
    first = [p.model_dump_json() for p in summarise(rows, GENERATOR_VERSION)]
    assert first == [p.model_dump_json() for p in summarise(rows, GENERATOR_VERSION)]


def test_placeholders_are_left_out_and_empty_chance_quality_is_kept():
    match = played("comeback", 1)
    r = reader(match)
    rows = [m for c, e in cadence(detect(r), match.end_clock_ms) for m in measure(r, e, c)]
    counted = {p.signal: p.sample_size for p in summarise(rows, GENERATOR_VERSION)}
    for signal in SIGNALS:
        assert counted[signal] == sum(m.signal is signal and not is_placeholder(m) for m in rows)
    chance = [m for m in rows if m.signal is Signal.CHANCE_QUALITY]
    assert counted[Signal.CHANCE_QUALITY] == len(chance)
    assert any(m.n == 0 for m in chance)


def test_the_generator_version_pins_what_the_comeback_generates():
    assert (GENERATOR_VERSION, _digest("comeback")) == ("generator-2", DIGESTS["comeback"])


@pytest.mark.slow
def test_the_generator_version_pins_every_archetype():
    assert GENERATOR_VERSION == "generator-2"
    assert {a: _digest(a) for a in sorted(ARCHETYPES)} == DIGESTS


@pytest.mark.slow
def test_rebuilding_the_sample_reproduces_the_committed_priors():
    """Same seeds, byte-identical priors: the numbers are reproducible, not just present."""
    assert priors_for(DOCUMENT["sample"], workers=4) == DOCUMENT["priors"]
