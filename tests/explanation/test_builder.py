"""L7: the rule-built claims, on the demo match and on every archetype.

Every metric is recounted here from the rows a claim cites, independently of the builder, so a
claim whose value its evidence does not back fails here before A3 exists to catch it.
"""

import typing
from dataclasses import dataclass
from pathlib import Path

import pytest

from matchlens import explanation
from matchlens.ingest import FrozenLog, Ingest
from matchlens.models import (
    Action,
    Claim,
    ClaimType,
    Epoch,
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
from matchlens.understanding.buildup import BALL_WINNING, lateral, shot_distance, win_third
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
    epochs: tuple[Epoch, ...]
    ingest: Ingest
    logs: list[FrozenLog]


def _play(
    seed: int,
    archetype=ARCHETYPES["comeback"],
    poison: Played | None = None,
    proposer: explanation.Proposer | None = None,
) -> Played:
    """`poison` is a finished match: each frozen log is built from all of it, future included.

    `proposer` is A2's model, if any.
    """
    items = list(simulate(seed, archetype))
    ingest = Ingest()
    understanding = Understanding(ingest.record)
    spotter = Spotter(ingest.record, understanding.epoch_at)
    readings: list[SignalReading] = []
    explained = []
    logs = []
    everything = [i for i in items if isinstance(i, Event)]
    for item in items:
        ingest.accept(item)
        if isinstance(item, MatchSetup):
            continue
        batch = understanding.observe(item)
        readings.extend(batch)
        for result in spotter.consider(batch, item):
            moment = result.moment
            if poison is None:
                log = FrozenLog(moment, ingest.record(), readings, understanding.epochs)
            else:
                log = FrozenLog(
                    moment, poison.ingest.record(), poison.readings.values(), poison.epochs
                )
            logs.append(log)
            explained.append(Explained(moment, explanation.explain(moment, log, proposer)))
    events = {e.event_id: e for e in everything}
    by_id = {r.reading_id: r for r in readings}
    return Played(explained, events, by_id, understanding.epochs, ingest, logs)


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
    if operand.metric is Metric.BALL_WON_THIRD:
        [win] = cited
        assert win.action in BALL_WINNING and win.team == operand.subject.id
        return float(win_third(match, win))
    if operand.metric is Metric.BALL_LOST:
        [lost] = cited
        assert lost.player == operand.subject.id
        return 1.0
    if operand.metric is Metric.SHOT_DISTANCE:
        [shot] = cited
        return shot_distance(match, shot)
    if operand.metric is Metric.BALL_LOST_BY_KEEPER:
        [lost] = cited
        assert lost.player == operand.subject.id
        return 1.0
    if operand.metric is Metric.ASSIST:
        pass_, shot = cited
        assert pass_.action is Action.PASS and pass_.receiver == shot.player
        assert is_shot(shot) and pass_.team == shot.team
        return 1.0
    if operand.metric in (Metric.SHOT_SAVED_BY, Metric.SHOT_BLOCKED_BY):
        shot, stop = cited
        wanted = Action.SAVE if operand.metric is Metric.SHOT_SAVED_BY else Action.BLOCK
        assert is_shot(shot) and stop.action is wanted and stop.team != shot.team
        return 1.0
    if operand.metric is Metric.PRESSURED_LOSS:
        [lost] = cited
        assert lost.player == operand.subject.id and lost.under_pressure is True
        return 1.0
    if operand.metric is Metric.SWITCH_OF_PLAY:
        [pass_] = cited
        assert pass_.action is Action.PASS and pass_.team == operand.subject.id
        return lateral(pass_) or 0.0
    if operand.metric is Metric.REGAIN:
        lost, won = cited
        assert lost.team == won.team == operand.subject.id and won.action in BALL_WINNING
        return (won.clock_ms - lost.clock_ms) / 1000
    if operand.metric is Metric.COMBINATION:
        first, second, shot = cited
        assert is_shot(shot) and first.receiver == second.player and second.receiver == shot.player
        return 3.0
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


def _bytes(played: Played) -> list[list[str]]:
    return [[c.model_dump_json() for c in x.claims] for x in played.explained]


def test_the_explainer_cannot_see_the_future(seed_1):
    # V2. Every frozen log here is built from the finished match: every event, reading and epoch
    # after the moment is in what it was handed. Claims byte-identical to the live run's prove
    # the log served none of it, since explain() has no filter of its own to have caught it.
    poisoned = _play(1, poison=seed_1)
    late = max(e.clock_ms for e in seed_1.events.values())
    assert any(x.moment.clock_ms < late for x in poisoned.explained)  # there was a future to see
    assert _bytes(poisoned) == _bytes(seed_1)


def test_a_moment_can_cite_the_event_at_its_own_clock(seed_1):
    # Inclusive at the boundary (Q6): a goal moment's clock is its goal's, and the goal is cited.
    goals = [x for x in seed_1.explained if x.moment.type is MomentType.GOAL]
    assert goals
    for x in goals:
        [trigger] = x.moment.trigger_event_ids
        assert seed_1.events[trigger].clock_ms == x.moment.clock_ms
        assert any(trigger in _cited(c) for c in x.claims)


def test_a_log_frozen_at_another_clock_is_refused(seed_1):
    first = seed_1.explained[0]
    later = next(log for log in seed_1.logs if log.clock_ms > first.moment.clock_ms)
    with pytest.raises(ValueError, match="frozen at"):
        explanation.explain(first.moment, later)


def test_the_same_seed_makes_identical_claims(seed_1):
    assert [x.claims for x in _play(1).explained] == [x.claims for x in seed_1.explained]


def test_every_claim_says_which_rules_made_it(seed_1):
    for x in seed_1.explained:
        for claim in x.claims:
            assert (claim.model, claim.model_version) == ("deterministic", "claims-7")


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
