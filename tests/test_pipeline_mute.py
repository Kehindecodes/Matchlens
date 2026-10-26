"""P2: a mute is a record of silence, decided before Selection (Q44: 1A, 2B).

The pipeline asks Control about each lens before it selects. A muted lens gets a suppressed
rendition with reason `muted` (invariant 11), spends none of its rate limit, and every other
lens is exactly what it was.
"""

import pytest

from apps import pipeline
from matchlens.control import Mutes
from matchlens.models import SuppressionReason
from matchlens.rendering import Card, MomentOutcome
from tests.test_pipeline_outcomes import _content, _items

MINUTE = 60_000
ANALYST = "match_analyst"
WINDOW = (20 * MINUTE, 30 * MINUTE)


def _run(mutes: Mutes | None = None) -> tuple[list[MomentOutcome], list[Card]]:
    outcomes: list[MomentOutcome] = []
    the_pipeline = pipeline.Pipeline(report=outcomes.append, mutes=mutes)
    cards = [card for item in _items() for card in the_pipeline.process(item)]
    return outcomes, cards


def _analyst(outcomes: list[MomentOutcome]):
    for moment in outcomes:
        yield moment, next(outcome for outcome in moment.outcomes if outcome.lens_id == ANALYST)


def _in_window(clock_ms: int) -> bool:
    return WINDOW[0] <= clock_ms < WINDOW[1]


@pytest.fixture(scope="module")
def baseline() -> tuple[list[MomentOutcome], list[Card]]:
    return _run()


@pytest.fixture(scope="module")
def muted_for_ten_minutes() -> tuple[list[MomentOutcome], list[Card]]:
    mutes = Mutes()
    mutes.mute(ANALYST, WINDOW[0], "ops", "wrong player named")
    mutes.unmute(ANALYST, WINDOW[1], "ops", "fixed")
    return _run(mutes)


def test_the_baseline_has_analyst_cards_in_the_window_or_the_rest_proves_nothing(baseline):
    _, cards = baseline
    assert any(
        _in_window(card.display_at_clock) and card.rendition.lens_id == ANALYST for card in cards
    )


def test_a_muted_lens_has_a_muted_rendition_for_every_moment_inside_the_mute(
    muted_for_ten_minutes,
):
    outcomes, _ = muted_for_ten_minutes
    inside = [
        (moment, lens_outcome)
        for moment, lens_outcome in _analyst(outcomes)
        if _in_window(moment.clock_ms)
    ]
    assert inside
    for moment, lens_outcome in inside:
        assert lens_outcome.rendition.suppressed, moment.moment_id
        assert lens_outcome.rendition.suppression_reason is SuppressionReason.MUTED


def test_nothing_is_muted_outside_the_mute(muted_for_ten_minutes):
    outcomes, _ = muted_for_ten_minutes
    outside = [
        lens_outcome
        for moment, lens_outcome in _analyst(outcomes)
        if not _in_window(moment.clock_ms)
    ]
    assert outside
    reasons = {lens_outcome.rendition.suppression_reason for lens_outcome in outside}
    assert SuppressionReason.MUTED not in reasons


def test_the_muted_lens_sends_no_card_inside_the_mute_and_no_other_lens_loses_one(
    baseline, muted_for_ten_minutes
):
    _, plain_cards = baseline
    _, muted_cards = muted_for_ten_minutes
    assert not [
        card
        for card in muted_cards
        if card.rendition.lens_id == ANALYST and _in_window(card.display_at_clock)
    ]

    def others(cards: list[Card]) -> list[str]:
        return [_content(card) for card in cards if card.rendition.lens_id != ANALYST]

    assert others(muted_cards) == others(plain_cards)


def test_a_muted_lens_spends_none_of_its_rate_limit_while_muted(muted_for_ten_minutes):
    outcomes, _ = muted_for_ten_minutes
    counts = [
        lens_outcome.shown_in_window
        for moment, lens_outcome in _analyst(outcomes)
        if _in_window(moment.clock_ms)
    ]
    assert counts == sorted(counts, reverse=True)  # only ever falling: nothing was shown


def test_a_lens_muted_now_is_muted_for_every_moment_the_pipeline_handles():
    # Q44: 2B. The pipeline decides when it handles the moment, so a click stops what is in flight.
    mutes = Mutes()
    mutes.mute(ANALYST, 40 * MINUTE, "ops", "wrong player named")
    outcomes, cards = _run(mutes)
    reasons = {lens_outcome.rendition.suppression_reason for _, lens_outcome in _analyst(outcomes)}
    assert reasons == {SuppressionReason.MUTED}
    assert not [card for card in cards if card.rendition.lens_id == ANALYST]


def test_a_pipeline_with_no_mutes_is_what_it_was(baseline):
    outcomes, _ = baseline
    reasons = {
        lens_outcome.rendition.suppression_reason
        for moment in outcomes
        for lens_outcome in moment.outcomes
    }
    assert SuppressionReason.MUTED not in reasons
