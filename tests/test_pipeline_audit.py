"""P3 (Q45: 1B, 2A): the pipeline leaves a moment's trail in Audit, and only the card path's.

Each moment is recorded once, as the pipeline finishes with it, with the claims it put to the
verifier, their verdicts, and what every lens did with it. A model's answer that was asked for only
to be scored, because the model was already down the ladder, never reached a card and is not in it.
"""

import threading
from typing import override

import pytest

from apps import pipeline
from matchlens import lenses
from matchlens.audit import Audit
from matchlens.control.ladder import Ladder
from matchlens.explanation import Answer
from matchlens.models import Verdict
from matchlens.rendering import Card, MomentOutcome
from tests.explanation.test_agent import Liar
from tests.test_pipeline_outcomes import _items

DETERMINISTIC = "deterministic"  # L7's claim builder, as opposed to a model's claims


class CountingLiar(Liar):
    """A2 lying about every number, counting how often it was asked."""

    def __init__(self) -> None:
        self.asked = 0
        self._lock = threading.Lock()

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        with self._lock:
            self.asked += 1
        return super().propose(instructions, prompt)


@pytest.fixture(scope="module")
def alone() -> tuple[Audit, list[MomentOutcome]]:
    """Seed 1's first fifty minutes with no model: L7's claims and L3's words."""
    audit, outcomes = Audit(), []
    the_pipeline = pipeline.Pipeline(report=outcomes.append, audit=audit)
    for item in _items():
        for _ in the_pipeline.process(item):
            pass
    return audit, outcomes


@pytest.fixture(scope="module")
def lied_to() -> tuple[Audit, CountingLiar, Ladder]:
    """The same fifty minutes with an A2 whose numbers are all wrong."""
    audit, liar, ladder = Audit(), CountingLiar(), Ladder()
    cards: list[Card] = []
    the_pipeline = pipeline.Pipeline(liar, cards.append, ladder=ladder, audit=audit)
    try:
        for item in _items():
            for _ in the_pipeline.process(item):
                pass
        the_pipeline.drain()
    finally:
        the_pipeline.close()
    return audit, liar, ladder


def test_every_moment_the_pipeline_reports_is_in_the_trail_in_the_same_order(alone):
    audit, outcomes = alone

    assert outcomes
    assert [entry.moment.moment_id for entry in audit.trail()] == [
        outcome.moment_id for outcome in outcomes
    ]


def test_each_moment_keeps_the_rendition_every_lens_made_including_the_silent_ones(alone):
    audit, outcomes = alone

    for entry, outcome in zip(audit.trail(), outcomes, strict=True):
        assert [rendition.lens_id for rendition in entry.renditions] == [
            lens.lens_id for lens in lenses.all_lenses()
        ]
        assert list(entry.renditions) == [lens.rendition for lens in outcome.outcomes]
    assert any(rendition.suppressed for entry in audit.trail() for rendition in entry.renditions)


def test_every_claim_of_every_moment_has_a_verdict_and_l7s_all_pass(alone):
    audit, _ = alone

    claims = [claim for entry in audit.trail() for claim in entry.claims]
    verdicts = [verdict for entry in audit.trail() for verdict in entry.verifications]
    assert claims and {claim.claim_id for claim in claims} == {
        verdict.claim_id for verdict in verdicts
    }
    assert {verdict.verdict for verdict in verdicts} == {Verdict.PASS}


def test_the_names_of_the_teams_and_players_come_from_the_match_setup(alone):
    audit, _ = alone

    assert audit.names
    claim_subjects = {
        operand.subject.id
        for entry in audit.trail()
        for claim in entry.claims
        for operand in claim.operands
    }
    assert claim_subjects <= set(audit.names)


def test_a_pipeline_given_no_audit_keeps_one_of_its_own():
    the_pipeline = pipeline.Pipeline()
    for item in _items():
        for _ in the_pipeline.process(item):
            pass

    assert the_pipeline.audit.trail()


def test_the_claims_a_model_got_wrong_are_in_the_trail_as_rejections_beside_l7s_that_passed(
    lied_to,
):
    audit, _, _ = lied_to

    verdicts = {
        verdict.claim_id: verdict for entry in audit.trail() for verdict in entry.verifications
    }
    modelled = [
        claim for entry in audit.trail() for claim in entry.claims if claim.model != DETERMINISTIC
    ]
    assert modelled
    assert all(verdicts[claim.claim_id].verdict is Verdict.FAIL for claim in modelled)
    kept = [
        claim for entry in audit.trail() for claim in entry.claims if claim.model == DETERMINISTIC
    ]
    assert kept and all(verdicts[claim.claim_id].verdict is Verdict.PASS for claim in kept)


def test_an_answer_asked_for_only_to_be_scored_is_not_in_the_trail(lied_to):
    audit, liar, ladder = lied_to

    moments_with_a_model_claim = {
        entry.moment.moment_id
        for entry in audit.trail()
        for claim in entry.claims
        if claim.model != DETERMINISTIC
    }
    assert not ladder.explainer.up  # A3's rejections switched the model off the ladder
    assert moments_with_a_model_claim
    # It went on being asked, as A5 has it, and each answer was scored and left out of the trail.
    assert liar.asked > len(moments_with_a_model_claim)
