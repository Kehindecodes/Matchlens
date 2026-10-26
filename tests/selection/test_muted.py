"""P2: a muted lens is suppressed as `muted`, decided before anything else about the moment
(Q44: 1A, and the order in DATA-MODEL: out of scope, then muted, then everything else)."""

from matchlens.models import MomentType, SuppressionReason
from matchlens.selection import ShownCards, select
from tests.selection.test_selection import ANALYST, CASUAL, _claim, _moment


def test_a_muted_lens_is_suppressed_as_muted_even_for_a_goal():
    goal = _moment(1.0, MomentType.GOAL)
    selected = select(goal, [_claim()], ANALYST, ShownCards(), muted=True)
    assert selected.claims == ()
    assert selected.suppression_reason is SuppressionReason.MUTED


def test_muted_outranks_every_reason_that_would_have_applied():
    quiet = _moment(0.0)  # below the casual threshold
    assert select(quiet, [_claim()], CASUAL, ShownCards()).suppression_reason is (
        SuppressionReason.BELOW_THRESHOLD
    )
    assert select(quiet, [], CASUAL, ShownCards(), muted=True).suppression_reason is (
        SuppressionReason.MUTED
    )


def test_a_muted_lens_spends_none_of_its_rate_limit():
    shown = ShownCards()
    select(_moment(0.9), [_claim()], ANALYST, shown, muted=True)
    assert shown.in_window(ANALYST.lens_id, 0) == 0


def test_a_lens_that_is_not_muted_is_selected_as_before():
    selected = select(_moment(0.9), [_claim()], ANALYST, ShownCards(), muted=False)
    assert selected.suppression_reason is None and selected.claims


def test_the_selection_still_carries_the_importance_the_lens_judged():
    selected = select(_moment(0.9), [_claim()], ANALYST, ShownCards(), muted=True)
    assert selected.importance == 0.9
