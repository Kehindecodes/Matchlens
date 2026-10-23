"""L7: the rule-built claims, on the demo match and on every archetype.

Every metric is recounted here from the rows a claim cites, independently of the builder, so a
claim whose value its evidence does not back fails here before A3 exists to catch it.
"""

import typing
from dataclasses import dataclass
from pathlib import Path

import pytest

from matchlens import explanation
from matchlens.ingest import Ingest
from matchlens.models import (
    Action,
    Claim,
    ClaimType,
    Event,
    Metric,
    Moment,
    MomentType,
    Outcome,
    RefKind,
    SignalReading,
)
from matchlens.source import MatchSetup, simulate
from matchlens.source.archetypes import ARCHETYPES
from matchlens.spotting import Spotter
from matchlens.understanding import Understanding
from matchlens.understanding.shot_value import is_shot, value

SIGNALS = {Metric.TERRITORY, Metric.POSSESSION_CONTROL, Metric.PRESSING_INTENSITY,
           Metric.CHANCE_QUALITY}  # fmt: skip


@dataclass
class Explained:
    moment: Moment
    claims: list[Claim]


@dataclass
class Played:
    explained: list[Explained]
    events: dict[str, Event]
    readings: dict[str, SignalReading]
    ingest: Ingest


def _play(seed: int, archetype=ARCHETYPES["comeback"], future: bool = False) -> Played:
    """`future` hands the explainer the whole match each time, to prove it reads none of it."""
    items = list(simulate(seed, archetype))
    ingest = Ingest()
    understanding = Understanding(ingest.record)
    spotter = Spotter(ingest.record, understanding.epoch_at)
    readings: list[SignalReading] = []
    explained = []
    everything = [i for i in items if isinstance(i, Event)]
    for item in items:
        ingest.accept(item)
        if isinstance(item, MatchSetup):
            continue
        batch = understanding.observe(item)
        readings.extend(batch)
        for result in spotter.consider(batch, item):
            moment = result.moment
            log = everything if future else ingest.record().events_between(0, moment.clock_ms + 1)
            claims = explanation.explain(
                moment, log, readings, understanding.epochs, ingest.record().match
            )
            explained.append(Explained(moment, claims))
    events = {e.event_id: e for e in everything}
    return Played(explained, events, {r.reading_id: r for r in readings}, ingest)


@pytest.fixture(scope="module")
def seed_1() -> Played:
    return _play(1)


def _cited(claim: Claim) -> set[str]:
    return {ref.id for operand in claim.operands for ref in operand.evidence_ids}


def _recount(operand, played: Played) -> float:
    ids = [ref.id for ref in operand.evidence_ids]
    match = played.ingest.record().match
    if operand.metric in SIGNALS:
        [reading] = [played.readings[i] for i in ids]
        assert reading.signal.value == operand.metric.value
        assert reading.team == operand.subject.id
        return reading.value
    cited = [played.events[i] for i in ids]
    assert all(operand.window.start_ms <= e.clock_ms <= operand.window.end_ms for e in cited)
    if operand.metric is Metric.GOALS:
        key = "player" if operand.subject.kind is RefKind.PLAYER else "team"
        assert all(
            e.outcome is Outcome.GOAL and getattr(e, key) == operand.subject.id for e in cited
        )
        return float(len(cited))
    if operand.metric is Metric.SHOT_QUALITY:
        [shot] = cited
        return value(shot, match).value
    if operand.metric is Metric.CHANCES:
        assert all(is_shot(e) and e.team == operand.subject.id for e in cited)
        return float(sum(value(e, match).value >= 0.25 for e in cited))
    if operand.metric is Metric.BUILD_UP_PASSES:
        return float(sum(e.action is Action.PASS for e in cited))
    raise AssertionError(operand.metric)


def test_every_moment_gets_at_least_one_claim(seed_1):
    assert seed_1.explained
    for x in seed_1.explained:
        assert x.claims, x.moment.moment_id


def test_every_value_recounts_from_its_cited_evidence(seed_1):
    for x in seed_1.explained:
        for claim in x.claims:
            for operand in claim.operands:
                assert _recount(operand, seed_1) == pytest.approx(operand.value), claim.claim_id


def test_every_trigger_is_cited_by_one_of_the_moments_claims(seed_1):
    for x in seed_1.explained:
        cited = set().union(*(_cited(c) for c in x.claims))
        triggers = {*x.moment.trigger_reading_ids, *x.moment.trigger_event_ids}
        assert triggers <= cited, x.moment.moment_id


def test_a_goal_names_its_scorer(seed_1):
    goals = [x for x in seed_1.explained if x.moment.type is MomentType.GOAL]
    assert goals
    for x in goals:
        scorer = x.claims[0].operands[0]
        assert scorer.subject.kind is RefKind.PLAYER
        assert scorer.subject.id == seed_1.events[x.moment.trigger_event_ids[0]].player


def test_a_score_line_is_only_claimed_when_both_sides_have_scored(seed_1):
    for x in seed_1.explained:
        for claim in x.claims:
            if (
                claim.operands[0].metric is Metric.GOALS
                and claim.claim_type is ClaimType.COMPARATIVE
            ):
                assert all(o.value >= 1 for o in claim.operands)


def test_an_interpretive_claim_is_backed_by_the_reading_that_fired_it(seed_1):
    shifts = [x for x in seed_1.explained if x.moment.type is MomentType.TACTICAL_SHIFT]
    for x in shifts:
        for claim in x.claims:
            if claim.claim_type is ClaimType.INTERPRETIVE:
                fired = seed_1.readings[x.moment.trigger_reading_ids[0]]
                assert claim.backing_reading.id == fired.reading_id
                assert (claim.threshold > 0) == (fired.z_match > 0)
                assert abs(fired.z_match) >= abs(claim.threshold)


def test_the_explainer_reads_nothing_after_the_moments_clock(seed_1):
    with_future = _play(1, future=True)
    assert [x.claims for x in with_future.explained] == [x.claims for x in seed_1.explained]


def test_the_same_seed_makes_identical_claims(seed_1):
    assert [x.claims for x in _play(1).explained] == [x.claims for x in seed_1.explained]


def test_every_claim_says_which_rules_made_it(seed_1):
    for x in seed_1.explained:
        for claim in x.claims:
            assert (claim.model, claim.model_version) == ("deterministic", "claims-1")


@pytest.mark.slow
@pytest.mark.parametrize("archetype", ARCHETYPES)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_every_archetype_is_explained_and_recounts(archetype, seed):
    played = _play(seed, ARCHETYPES[archetype])
    for x in played.explained:
        assert x.claims, x.moment.moment_id
        for claim in x.claims:
            for operand in claim.operands:
                assert _recount(operand, played) == pytest.approx(operand.value)


def test_nothing_the_explainer_is_handed_can_hold_a_frame():
    # Invariant 1: the explainer's inputs are events, readings, epochs and the match setup.
    hints = typing.get_type_hints(explanation.explain)
    banned = {"Frame", "FrameWindow", "FrameAccess", "Ingest", "RecordReader"}
    assert not any(name in str(hint) for hint in hints.values() for name in banned), hints


def test_the_word_for_shot_quality_is_never_the_other_one_in_the_explainer():
    needle = "x" + "G"
    root = Path(explanation.__file__).parent
    assert not [p.name for p in root.rglob("*.py") if needle in p.read_text()]
