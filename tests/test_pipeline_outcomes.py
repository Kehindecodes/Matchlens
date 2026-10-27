"""P1: the pipeline says, for every moment, what each lens did with it (Q43: 1A, 2A).

The producer view needs what a viewer never gets: the suppressed renditions, the importance each
lens judged and the rate-limit state. None of it changes a card.
"""

import itertools
import logging
import threading

import pytest

from apps import pipeline
from matchlens import lenses
from matchlens.control.ladder import Ladder
from matchlens.models import MomentType, SuppressionReason
from matchlens.rendering import Card, LensOutcome, MomentOutcome
from matchlens.selection.outcome import TEN_MINUTES_MS
from matchlens.source import simulate
from matchlens.source.archetypes import COMEBACK
from tests.rendering.test_writer import Echo

# Seed 1 on the comeback, the whole match: goals, chances and shifts. It is the match these tests
# were written on, and the one that crowds a lens enough to rate-limit it; under `generator-2`
# that happens after the 70th minute, so the first 50 no longer do (Q48).
_UNTIL_MS = 100 * 60_000


def _items():
    return itertools.takewhile(
        lambda item: getattr(item, "clock_ms", 0) < _UNTIL_MS, simulate(1, COMEBACK)
    )


def _content(card: Card) -> str:
    return card.model_dump_json(exclude={"rendition": {"rendered_at"}})


def _run_alone(report=None) -> list[Card]:
    the_pipeline = pipeline.Pipeline(report=report)
    return [card for item in _items() for card in the_pipeline.process(item)]


@pytest.fixture(scope="module")
def reported() -> tuple[list[MomentOutcome], list[Card]]:
    """Seed 1 with no model, reporting: the outcomes and the cards that went out."""
    outcomes: list[MomentOutcome] = []
    cards = _run_alone(outcomes.append)
    return outcomes, cards


@pytest.fixture(scope="module")
def first_goal(reported) -> str:
    outcomes, _ = reported
    return next(outcome.moment_id for outcome in outcomes if outcome.moment_type is MomentType.GOAL)


def _every_lens_outcome(outcomes: list[MomentOutcome]):
    for moment_outcome in outcomes:
        for lens_outcome in moment_outcome.outcomes:
            yield moment_outcome, lens_outcome


def test_every_moment_reports_an_outcome_for_every_lens(reported):
    outcomes, _ = reported
    expected = tuple(lens.lens_id for lens in lenses.all_lenses())
    assert outcomes
    for moment_outcome in outcomes:
        assert moment_outcome.lens_ids == expected
        assert tuple(lens_outcome.lens_id for lens_outcome in moment_outcome.outcomes) == expected
        assert moment_outcome.failure is None


def test_the_outcomes_are_in_the_order_the_moments_fired(reported):
    outcomes, _ = reported
    clocks = [moment_outcome.clock_ms for moment_outcome in outcomes]
    assert clocks == sorted(clocks)
    assert len({moment_outcome.moment_id for moment_outcome in outcomes}) == len(outcomes)


def test_a_lens_that_said_nothing_has_a_suppressed_rendition_with_its_reason(reported):
    # Invariant 11, observable: silence arrives as a record, not as a gap.
    outcomes, _ = reported
    silent = [
        lens_outcome
        for _, lens_outcome in _every_lens_outcome(outcomes)
        if lens_outcome.rendition.suppressed
    ]
    assert silent
    assert all(lens_outcome.rendition.suppression_reason is not None for lens_outcome in silent)
    reasons = {lens_outcome.rendition.suppression_reason for lens_outcome in silent}
    assert len(reasons) > 1  # not one reason repeated


def test_the_outcomes_that_spoke_are_exactly_the_cards_that_went_out(reported):
    outcomes, cards = reported
    spoke = [
        lens_outcome.rendition.rendition_id
        for _, lens_outcome in _every_lens_outcome(outcomes)
        if not lens_outcome.rendition.suppressed
    ]
    assert spoke == [card.rendition.rendition_id for card in cards]


def test_the_importance_is_what_the_lens_judged_against_its_own_threshold(reported):
    outcomes, _ = reported
    rows = {lens.lens_id: lens for lens in lenses.all_lenses()}
    for _, lens_outcome in _every_lens_outcome(outcomes):
        threshold = rows[lens_outcome.lens_id].importance_threshold
        rendition = lens_outcome.rendition
        if rendition.suppression_reason is SuppressionReason.BELOW_THRESHOLD:
            assert lens_outcome.importance < threshold
        elif not rendition.suppressed:
            assert lens_outcome.importance >= threshold


def test_the_rate_limit_count_is_the_cards_the_lens_showed_in_its_last_ten_minutes(reported):
    outcomes, _ = reported
    rows = {lens.lens_id: lens for lens in lenses.all_lenses()}
    shown_at: dict[str, list[int]] = {lens_id: [] for lens_id in rows}
    limited = 0
    for moment_outcome in outcomes:
        for lens_outcome in moment_outcome.outcomes:
            if not lens_outcome.rendition.suppressed:
                shown_at[lens_outcome.lens_id].append(moment_outcome.clock_ms)
            in_window = [
                clock
                for clock in shown_at[lens_outcome.lens_id]
                if moment_outcome.clock_ms - TEN_MINUTES_MS < clock <= moment_outcome.clock_ms
            ]
            where = (moment_outcome.moment_id, lens_outcome.lens_id)
            assert lens_outcome.shown_in_window == len(in_window), where
            if lens_outcome.rendition.suppression_reason is SuppressionReason.RATE_LIMITED:
                limited += 1
                limit = rows[lens_outcome.lens_id].max_cards_per_10min
                assert lens_outcome.shown_in_window >= limit
    assert limited, "seed 1 should rate-limit a lens, or this test proves nothing"


def test_reporting_changes_no_card(reported):
    _, cards = reported
    unreported = _run_alone()
    assert [_content(card) for card in cards] == [_content(card) for card in unreported]


def test_a_lens_rendering_failed_on_reports_a_degraded_rendition_not_a_gap(
    reported, first_goal, monkeypatch
):
    # A5 turns a Rendering failure into a record. The producer view has to be told about it.
    real = pipeline.render

    def render(moment, *args, **kwargs):
        if moment.moment_id == first_goal:
            raise RuntimeError("a template that does not format")
        return real(moment, *args, **kwargs)

    monkeypatch.setattr(pipeline, "render", render)
    outcomes: list[MomentOutcome] = []
    _run_alone(outcomes.append)

    failed = next(outcome for outcome in outcomes if outcome.moment_id == first_goal)
    assert failed.failure is None  # the moment completed; it was its lenses that could not render
    assert len(failed.outcomes) == len(failed.lens_ids)
    reasons = {lens_outcome.rendition.suppression_reason for lens_outcome in failed.outcomes}
    assert SuppressionReason.DEGRADED in reasons


def test_a_moment_that_fails_outside_rendering_is_reported_failed_and_is_not_silent(
    reported, first_goal, monkeypatch, caplog
):
    plain_outcomes, _ = reported
    real = pipeline.selection.select

    def select(moment, *args, **kwargs):
        if moment.moment_id == first_goal:
            raise RuntimeError("selection exploded")
        return real(moment, *args, **kwargs)

    monkeypatch.setattr(pipeline.selection, "select", select)
    outcomes: list[MomentOutcome] = []
    cards: list[Card] = []
    reports_done = threading.Event()

    def report(outcome: MomentOutcome) -> None:
        outcomes.append(outcome)
        if len(outcomes) == len(plain_outcomes):
            reports_done.set()

    # A model makes the editorial stages run on their own thread, where this failure used to
    # vanish into a future nobody read.
    the_pipeline = pipeline.Pipeline(
        writer=Echo(), publish=cards.append, ladder=Ladder(), report=report
    )
    with caplog.at_level(logging.ERROR):
        try:
            for item in _items():
                for _ in the_pipeline.process(item):
                    pass
            assert reports_done.wait(60), "every moment should report, failed or not"
            with pytest.raises(RuntimeError, match="selection exploded"):
                the_pipeline.drain()  # still raised for whoever drains
        finally:
            the_pipeline.close()

    failed = [outcome for outcome in outcomes if outcome.failure is not None]
    assert [outcome.moment_id for outcome in failed] == [first_goal]
    [failure] = failed
    assert failure.failure == "RuntimeError: selection exploded"
    # No lens has a rendition for it: the broken state, which a quiet lens never is.
    assert failure.outcomes == ()
    assert failure.lens_ids == tuple(lens.lens_id for lens in lenses.all_lenses())
    # Viewers are unchanged: no card from the moment, and the others carry on.
    assert not any(card.rendition.moment_id == first_goal for card in cards)
    assert all(outcome.outcomes for outcome in outcomes if outcome.failure is None)
    assert any(first_goal in record.getMessage() for record in caplog.records)


def test_a_lens_outcome_is_a_frozen_record(reported):
    outcomes, _ = reported
    lens_outcome = outcomes[0].outcomes[0]
    assert isinstance(lens_outcome, LensOutcome)
    with pytest.raises(ValueError):
        lens_outcome.importance = 0.0  # type: ignore[misc]
