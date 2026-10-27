"""A3: the six checks, on L7's claims first and on deliberately broken ones second.

Each broken claim is a real L7 claim from seed 1 with one thing changed, so a check that fails
it fails for that one thing.
"""

import math
import time
from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from matchlens import explanation, verification
from matchlens.config import settings
from matchlens.explanation import Proposer
from matchlens.ingest import FrozenLog, Ingest, pitch_window
from matchlens.models import (
    CheckName,
    CheckResult,
    CheckStatus,
    Claim,
    ClaimType,
    Metric,
    Moment,
    MomentType,
    Ref,
    RefKind,
    Verdict,
    Verification,
)
from matchlens.source import MatchSetup, simulate
from matchlens.source.archetypes import ARCHETYPES
from matchlens.spotting import Spotter
from matchlens.understanding import Movement, Understanding
from matchlens.verification import checks

# Seed 1 of the one-sided match: scored by m-1-home-p17, who came off the bench. The comeback has
# no substitute's goal under `generator-2` (Q48).
SUBSTITUTE_GOAL = "m-1-e1747"


@dataclass
class Explained:
    moment: Moment
    claims: list[Claim]
    record: verification.Record  # as it stood when the moment was explained


@dataclass
class Played:
    explained: list[Explained]
    whole: verification.Record  # the finished match, for claims about rows the moment never saw


def _play(seed: int = 1, archetype: str = "comeback", proposer: Proposer | None = None) -> Played:
    ingest = Ingest()
    understanding = Understanding(ingest.record)
    spotter = Spotter(ingest.record, understanding.epoch_at)
    movement = Movement(ingest.frame_access, ingest.record)
    readings = []
    positions = []
    explained = []
    for item in simulate(seed, ARCHETYPES[archetype]):
        ingest.accept(item)
        if isinstance(item, MatchSetup):
            continue
        batch = understanding.observe(item)
        readings.extend(batch)
        positions.extend(movement.observe(item))
        for result in spotter.consider(batch, item):
            reader = ingest.record()
            log = FrozenLog(result.moment, reader, readings, understanding.epochs, positions)
            claims = explanation.explain(result.moment, log, proposer)
            record = verification.Record.of(reader, readings, positions)
            explained.append(Explained(result.moment, claims, record))
    return Played(explained, verification.Record.of(ingest.record(), readings, positions))


@pytest.fixture(scope="module")
def seed_1() -> Played:
    return _play()


@pytest.fixture(scope="module")
def substitute() -> Played:
    return _play(1, "one_sided")


def _verify(x: Explained, claim: Claim, record: verification.Record | None = None) -> Verification:
    return verification.verify(claim, x.moment, x.claims, record or x.record)


def _goal(played: Played, event_id: str | None = None) -> Explained:
    return next(
        x
        for x in played.explained
        if x.moment.type is MomentType.GOAL
        and (event_id is None or x.moment.trigger_event_ids == (event_id,))
    )


def _with_operand(claim: Claim, n: int = 0, **changes) -> Claim:
    """`claim` with operand `n` changed: built with validation, so the change is a valid claim."""
    operands = list(claim.operands)
    operands[n] = operands[n].model_copy(update=changes)
    return Claim.model_validate(
        claim.model_dump() | {"operands": [o.model_dump() for o in operands]}
    )


def _status(v: Verification, check: CheckName) -> CheckStatus:
    return v.checks[check].status


# --- L7's claims pass ----------------------------------------------------------------------------


def test_every_l7_claim_on_seed_1_passes_all_six(seed_1):
    total = 0
    for x in seed_1.explained:
        for claim in x.claims:
            v = _verify(x, claim)
            assert v.verdict is Verdict.PASS, (claim.claim_id, v.failure_reason)
            assert set(v.checks) == set(CheckName)
            assert len(v.recomputed_value) == len(claim.operands)
            assert all(not math.isnan(f) for f in v.recomputed_value)
            total += 1
    assert total > 50


@pytest.mark.slow
@pytest.mark.parametrize("archetype", ARCHETYPES)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_every_l7_claim_on_every_archetype_passes(archetype, seed):
    played = _play(seed, archetype)
    for x in played.explained:
        for claim in x.claims:
            v = _verify(x, claim)
            assert v.verdict is Verdict.PASS, (claim.claim_id, v.failure_reason)


def test_a_verification_names_the_verifier(seed_1):
    x = seed_1.explained[0]
    v = _verify(x, x.claims[0])
    assert (v.model, v.model_version) == ("verifier", "checks-1")


# --- the record cannot be built wrong ------------------------------------------------------------


def _verification(**changes) -> dict:
    passed = CheckResult(status=CheckStatus.PASSED)
    return {
        "verification_id": "v",
        "claim_id": "c",
        "verdict": Verdict.PASS,
        "checks": dict.fromkeys(CheckName, passed),
        "recomputed_value": (1.0,),
        "failure_reason": None,
        "latency_ms": 0,
        "model": "verifier",
        "model_version": "checks-1",
    } | changes


@pytest.mark.parametrize("check", CheckName)
def test_a_verification_missing_any_check_cannot_be_constructed(check):
    passed = CheckResult(status=CheckStatus.PASSED)
    five = {name: passed for name in CheckName if name is not check}
    with pytest.raises(ValidationError, match="every check must run"):
        Verification(**_verification(checks=five))


def test_a_pass_with_a_failed_check_cannot_be_constructed():
    checks_ = dict.fromkeys(CheckName, CheckResult(status=CheckStatus.PASSED))
    checks_[CheckName.VALUE] = CheckResult(status=CheckStatus.FAILED, reason="wrong")
    with pytest.raises(ValidationError, match="verdict is pass iff"):
        Verification(**_verification(checks=checks_))


# --- value and entailment are different checks ---------------------------------------------------


def test_a_wrong_number_fails_value_with_the_recomputed_figure(seed_1):
    x = _goal(seed_1)
    scorer = x.claims[0]  # "his first goal": 1
    assert scorer.operands[0].metric is Metric.GOALS and scorer.operands[0].value == 1.0
    v = _verify(x, _with_operand(scorer, value=2.0))
    assert _status(v, CheckName.VALUE) is CheckStatus.FAILED
    assert v.recomputed_value == (1.0,)
    assert "is 1 in the record, not 2" in (v.checks[CheckName.VALUE].reason or "")
    assert v.verdict is Verdict.FAIL and v.failure_reason


def test_a_right_number_with_unrelated_citations_fails_entailment_and_passes_value(seed_1):
    # The test that proves value and entailment are two checks (D21).
    x = _goal(seed_1)
    scorer = x.claims[0]
    goal = seed_1.whole.event[x.moment.trigger_event_ids[0]]
    unrelated = next(
        e for e in reversed(x.record.until(goal.clock_ms - 1)) if e.team == goal.team and e.player
    )
    v = _verify(
        x, _with_operand(scorer, evidence_ids=(Ref(kind=RefKind.EVENT, id=unrelated.event_id),))
    )
    assert _status(v, CheckName.VALUE) is CheckStatus.PASSED
    assert _status(v, CheckName.CITATION) is CheckStatus.PASSED
    assert _status(v, CheckName.ENTAILMENT) is CheckStatus.FAILED
    assert unrelated.event_id in (v.checks[CheckName.ENTAILMENT].reason or "")


def test_a_signal_operand_citing_an_event_fails_entailment(seed_1):
    # What the live model did (docs/evidence/A2-live-seed1.txt): a reading's value, an event cited.
    x, claim = next(
        (x, c)
        for x in seed_1.explained
        for c in x.claims
        if x.moment.type is MomentType.TACTICAL_SHIFT and c.claim_type is not ClaimType.INTERPRETIVE
    )
    event = x.record.until(x.moment.clock_ms)[-1]
    v = _verify(x, _with_operand(claim, evidence_ids=(Ref(kind=RefKind.EVENT, id=event.event_id),)))
    assert _status(v, CheckName.VALUE) is CheckStatus.PASSED
    assert _status(v, CheckName.ENTAILMENT) is CheckStatus.FAILED


_POSITION_METRICS = (Metric.OVERLOAD, Metric.DECOY_RUN, Metric.EARLY_RUN)


def _position_claims(played: Played) -> list[tuple[Explained, Claim]]:
    return [
        (x, c)
        for x in played.explained
        for c in x.claims
        if c.operands[0].metric in _POSITION_METRICS
    ]


def test_seed_1_has_position_claims_and_each_cites_only_its_position_reading(seed_1):
    found = _position_claims(seed_1)
    assert found
    for x, claim in found:
        for operand in claim.operands:
            assert [r.kind for r in operand.evidence_ids] == [RefKind.POSITION]
            assert (
                x.record.position[operand.evidence_ids[0].id].shot_id in x.moment.trigger_event_ids
            )


def test_a_position_claim_with_a_wrong_figure_fails_value_and_entailment(seed_1):
    x, claim = _position_claims(seed_1)[0]
    v = _verify(x, _with_operand(claim, value=claim.operands[0].value + 3))
    assert _status(v, CheckName.VALUE) is CheckStatus.FAILED
    assert _status(v, CheckName.ENTAILMENT) is CheckStatus.FAILED
    assert v.recomputed_value[0] == claim.operands[0].value


def test_a_run_said_of_another_player_fails(seed_1):
    x, claim = next(
        (x, c) for x, c in _position_claims(seed_1) if c.operands[0].metric is not Metric.OVERLOAD
    )
    reading = x.record.position[claim.operands[0].evidence_ids[0].id]
    other = next(
        p.player_id
        for p in x.record.players
        if p.team_id == reading.team and p.player_id != reading.player
    )
    v = _verify(x, _with_operand(claim, subject=Ref(kind=RefKind.PLAYER, id=other)))
    assert v.verdict is Verdict.FAIL
    assert _status(v, CheckName.ENTAILMENT) is CheckStatus.FAILED
    assert "not about" in (v.checks[CheckName.ENTAILMENT].reason or "")


def test_a_position_claim_citing_an_event_instead_fails_entailment(seed_1):
    x, claim = _position_claims(seed_1)[0]
    shot = Ref(kind=RefKind.EVENT, id=x.moment.trigger_event_ids[0])
    v = _verify(x, _with_operand(claim, evidence_ids=(shot,)))
    assert _status(v, CheckName.VALUE) is CheckStatus.PASSED  # the record says the same figure
    assert _status(v, CheckName.ENTAILMENT) is CheckStatus.FAILED


def test_a_position_reading_that_is_not_in_the_record_fails_citation(seed_1):
    x, claim = _position_claims(seed_1)[0]
    made_up = Ref(kind=RefKind.POSITION, id="m-1-e0-decoy_run")
    v = _verify(x, _with_operand(claim, evidence_ids=(made_up,)))
    assert _status(v, CheckName.CITATION) is CheckStatus.FAILED


def test_an_interpretive_threshold_the_reading_does_not_clear_fails_entailment(seed_1):
    x, claim = next(
        (x, c) for x in seed_1.explained for c in x.claims if c.claim_type is ClaimType.INTERPRETIVE
    )
    assert claim.threshold is not None
    flipped = Claim.model_validate(claim.model_dump() | {"threshold": -claim.threshold})
    v = _verify(x, flipped)
    assert _status(v, CheckName.VALUE) is CheckStatus.PASSED
    assert _status(v, CheckName.ENTAILMENT) is CheckStatus.FAILED
    assert "does not clear" in (v.checks[CheckName.ENTAILMENT].reason or "")


# --- temporal ------------------------------------------------------------------------------------


def test_citing_an_event_after_the_clock_fails_temporal(seed_1):
    x = _goal(seed_1)
    later = next(e for e in seed_1.whole.events if e.clock_ms > x.moment.clock_ms)
    claim = _with_operand(x.claims[0], evidence_ids=(Ref(kind=RefKind.EVENT, id=later.event_id),))
    v = _verify(x, claim, seed_1.whole)
    assert _status(v, CheckName.CITATION) is CheckStatus.PASSED  # it exists, so it resolves
    assert _status(v, CheckName.TEMPORAL) is CheckStatus.FAILED
    assert later.event_id in (v.checks[CheckName.TEMPORAL].reason or "")


def test_citing_the_event_exactly_at_the_clock_passes_temporal(seed_1):
    x = _goal(seed_1)
    [trigger] = x.moment.trigger_event_ids
    assert seed_1.whole.event[trigger].clock_ms == x.moment.clock_ms
    claim = x.claims[0]
    assert Ref(kind=RefKind.EVENT, id=trigger) in claim.operands[0].evidence_ids
    assert _status(_verify(x, claim), CheckName.TEMPORAL) is CheckStatus.PASSED


def test_a_window_ending_after_the_clock_fails_temporal(seed_1):
    # A count over a window that runs on past the moment is a claim about the future, even
    # when every row it cites is in the past.
    x = _goal(seed_1)
    claim = x.claims[0]
    window = claim.operands[0].window.model_copy(update={"end_ms": x.moment.clock_ms + 60_000})
    v = _verify(x, _with_operand(claim, window=window), seed_1.whole)
    assert _status(v, CheckName.TEMPORAL) is CheckStatus.FAILED


# --- entity --------------------------------------------------------------------------------------


def test_entity_is_not_applicable_for_a_team_subject(seed_1):
    x = _goal(seed_1)
    team = next(c for c in x.claims if c.operands[0].subject.kind is RefKind.TEAM)
    assert _status(_verify(x, team), CheckName.ENTITY) is CheckStatus.NOT_APPLICABLE


def test_a_substitute_scorer_passes_entity_over_his_time_on_the_pitch(substitute):
    # Q36: B. His count runs from when he came on, so he was on the pitch across it.
    x = _goal(substitute, SUBSTITUTE_GOAL)
    scorer = x.claims[0]
    player = substitute.whole.player[scorer.operands[0].subject.id]
    assert not player.is_starter
    entered, _ = pitch_window(player, substitute.whole.events)
    assert scorer.operands[0].window.start_ms == entered > 0
    assert _status(_verify(x, scorer), CheckName.ENTITY) is CheckStatus.PASSED


def test_a_player_not_on_the_pitch_across_the_window_fails_entity(substitute):
    # The same claim over kickoff to the goal: he was on the bench for most of it.
    x = _goal(substitute, SUBSTITUTE_GOAL)
    scorer = x.claims[0]
    window = scorer.operands[0].window.model_copy(update={"start_ms": 0})
    v = _verify(x, _with_operand(scorer, window=window))
    assert _status(v, CheckName.ENTITY) is CheckStatus.FAILED
    assert _status(v, CheckName.VALUE) is CheckStatus.PASSED  # still his only goal


# --- coverage ------------------------------------------------------------------------------------


def _cited(claim: Claim) -> set[str]:
    refs = [r.id for o in claim.operands for r in o.evidence_ids]
    return {*refs, *([claim.backing_reading.id] if claim.backing_reading else [])}


def test_a_moment_whose_trigger_no_claim_cites_fails_coverage(seed_1):
    x = next(x for x in seed_1.explained if x.moment.type is MomentType.TACTICAL_SHIFT)
    [trigger] = x.moment.trigger_reading_ids
    assert all(trigger in _cited(c) for c in x.claims)  # L7 cites it in every shift claim
    # The moment's one claim, made to cite another reading of the same series instead.
    descriptive = next(c for c in x.claims if c.claim_type is not ClaimType.INTERPRETIVE)
    fired = x.record.reading[trigger]
    other = next(
        r
        for r in reversed(x.record.readings)
        if r.signal is fired.signal and r.team == fired.team and r.reading_id != trigger
    )
    moved = _with_operand(
        descriptive, evidence_ids=(Ref(kind=RefKind.READING, id=other.reading_id),)
    )
    v = verification.verify(moved, x.moment, [moved], x.record)
    assert _status(v, CheckName.COVERAGE) is CheckStatus.FAILED
    assert trigger in (v.checks[CheckName.COVERAGE].reason or "")


# --- fails closed --------------------------------------------------------------------------------


def test_a_check_that_raises_fails_and_the_verdict_with_it(seed_1, monkeypatch):
    def broken(claim, record):
        raise RuntimeError("the record is unreadable")

    monkeypatch.setattr(checks, "entailment", broken)
    x = seed_1.explained[0]
    v = _verify(x, x.claims[0])
    assert v.verdict is Verdict.FAIL
    assert _status(v, CheckName.ENTAILMENT) is CheckStatus.FAILED
    assert "the record is unreadable" in (v.checks[CheckName.ENTAILMENT].reason or "")


def test_running_out_of_budget_fails_what_has_not_run(seed_1, monkeypatch):
    monkeypatch.setattr(settings, "verifier_budget_ms", -1)  # already used up before it starts
    x = seed_1.explained[0]
    v = _verify(x, x.claims[0])
    assert v.verdict is Verdict.FAIL
    assert all(r.status is CheckStatus.FAILED for r in v.checks.values())
    assert "budget" in (v.failure_reason or "")


def test_a_pause_between_a_claims_checks_does_not_fail_it(seed_1, monkeypatch):
    # A garbage collection stops every thread, and in the suite's large process one lasts close
    # to a second. Landing between two checks, it used up the budget and dropped a claim from a
    # card, so a test comparing two runs failed on whichever claim it hit. The tests run with the
    # budget lifted (conftest) so that a slow machine cannot change what a run produces.
    real = checks.temporal

    def paused(claim, moment, record):
        time.sleep(0.6)  # longer than the 500 ms the setting ships with
        return real(claim, moment, record)

    monkeypatch.setattr(checks, "temporal", paused)
    x = seed_1.explained[0]
    v = _verify(x, x.claims[0])
    assert v.verdict is Verdict.PASS, v.failure_reason


def test_a_claim_that_does_not_validate_fails_every_check(seed_1):
    x = seed_1.explained[0]
    malformed = Claim.model_construct(**(x.claims[0].__dict__ | {"operands": ()}))
    v = _verify(x, malformed)
    assert v.verdict is Verdict.FAIL
    assert all(r.status is CheckStatus.FAILED for r in v.checks.values())
    assert "malformed claim" in (v.failure_reason or "")


def test_a_claim_about_another_moment_fails(seed_1):
    first, second = seed_1.explained[:2]
    v = verification.verify(first.claims[0], second.moment, second.claims, second.record)
    assert v.verdict is Verdict.FAIL


# --- the live budget -----------------------------------------------------------------------------


def test_every_claim_is_checked_well_inside_the_budget(seed_1):
    slowest = 0.0
    for x in seed_1.explained:
        for claim in x.claims:
            start = time.perf_counter()
            v = _verify(x, claim)
            slowest = max(slowest, (time.perf_counter() - start) * 1000)
            assert v.latency_ms >= 0
    # The suite lifts the live budget (conftest), so this holds the claims to the shipped one.
    shipped = type(settings).model_fields["verifier_budget_ms"].default
    assert slowest < shipped / 5, f"slowest claim took {slowest:.1f} ms"


# --- what the explainer's model gets wrong, A3 catches -----------------------------------------


def test_a2s_wrong_numbers_fail_value_and_its_right_ones_pass(seed_1):
    from tests.explanation.test_agent import Honest, Liar

    for model, verdict in ((Honest(), Verdict.PASS), (Liar(), Verdict.FAIL)):
        played = _play(proposer=model)
        proposed = [
            (x, c) for x in played.explained for c in x.claims if c.model != "deterministic"
        ]
        assert proposed
        for x, claim in proposed:
            v = _verify(x, claim)
            assert v.verdict is verdict, (claim.claim_id, v.failure_reason)
            if verdict is Verdict.FAIL:
                assert _status(v, CheckName.VALUE) is CheckStatus.FAILED
