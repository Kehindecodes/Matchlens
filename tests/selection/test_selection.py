"""L2: Selection chooses claims for one lens, and says why when it chooses none.

Constructed moments and lenses, one rule per test. The lenses come from the registry by depth
and are adjusted with `model_copy`, so nothing here names a preset. The last test runs the demo
match through the pipeline to see the rules working together.
"""

import subprocess
import sys

import pytest

from matchlens import lenses
from matchlens.config import settings
from matchlens.models import (
    Claim,
    ClaimType,
    Depth,
    Lens,
    Metric,
    Moment,
    MomentType,
    Operand,
    Ref,
    RefKind,
    Scope,
    SuppressionReason,
    Window,
)
from matchlens.selection import Selection, ShownCards, select

MINUTE = 60_000


def _lens(depth: Depth, **changes) -> Lens:
    lens = next(lens for lens in lenses.all_lenses() if lens.depth is depth)
    return lens.model_copy(update=changes)


CASUAL = _lens(Depth.CASUAL)
ANALYST = _lens(Depth.ANALYST)
TEAM = _lens(Depth.ENGAGED)
assert TEAM.focus_team is not None
FOCUS = Ref(kind=RefKind.TEAM, id=TEAM.focus_team)
OPPONENT = Ref(kind=RefKind.TEAM, id="the-other-side")


def _moment(
    importance: float,
    type_: MomentType = MomentType.TACTICAL_SHIFT,
    subject: Ref = FOCUS,
    clock_ms: int = 0,
    moment_id: str = "m",
) -> Moment:
    return Moment(
        moment_id=moment_id, clock_ms=clock_ms, type=type_, subject=subject,
        importance=importance, trigger_reading_ids=("r",), trigger_event_ids=(),
        epoch_id="e", model="spotter", model_version="1",
    )  # fmt: skip


def _claim(claim_type: ClaimType = ClaimType.DESCRIPTIVE, claim_id: str = "c") -> Claim:
    operand = Operand(
        subject=FOCUS, metric=Metric.CHANCES, window=Window(start_ms=0, end_ms=1), value=1.0,
        evidence_ids=(Ref(kind=RefKind.EVENT, id="ev"),),
    )  # fmt: skip
    interpretive = claim_type is ClaimType.INTERPRETIVE
    return Claim(
        claim_id=claim_id, moment_id="m", claim_type=claim_type,
        operands=(operand, operand) if claim_type is ClaimType.COMPARATIVE else (operand,),
        backing_reading=Ref(kind=RefKind.READING, id="r") if interpretive else None,
        threshold=1.0 if interpretive else None, model="m", model_version="v",
    )  # fmt: skip


def _select(moment: Moment, lens: Lens, claims: list[Claim] | None = None, shown=None):
    return select(
        moment,
        [_claim()] if claims is None else claims,
        lens,
        ShownCards() if shown is None else shown,
    )


# --- the threshold (V3) --------------------------------------------------------------------------


def test_a_moment_between_the_two_thresholds_is_shown_to_analyst_and_silent_for_casual():
    assert ANALYST.importance_threshold < CASUAL.importance_threshold
    middle = (ANALYST.importance_threshold + CASUAL.importance_threshold) / 2
    moment = _moment(middle)

    analyst = _select(moment, ANALYST)
    casual = _select(moment, CASUAL)

    assert [c.claim_id for c in analyst.claims] == ["c"]
    assert analyst.suppression_reason is None
    assert casual.claims == ()
    assert casual.suppression_reason is SuppressionReason.BELOW_THRESHOLD


def test_a_moment_exactly_on_the_threshold_clears_it():
    assert _select(_moment(ANALYST.importance_threshold), ANALYST).suppression_reason is None


# --- one reason, the first in the declared order (D14) -------------------------------------------


def test_a_selection_has_claims_or_a_reason_never_both_and_never_neither():
    with pytest.raises(ValueError):
        Selection(claims=(), suppression_reason=None, importance=0.5)
    with pytest.raises(ValueError):
        Selection(claims=(_claim(),), suppression_reason=SuppressionReason.MUTED, importance=0.5)


def _limited(lens: Lens) -> tuple[Lens, ShownCards]:
    """The lens, and a state in which it has already shown as many cards as it may."""
    shown = ShownCards()
    for _ in range(lens.max_cards_per_10min):
        shown.record(lens.lens_id, 0)
    return lens, shown


# Every reason that can apply at once, then fewer. The expected one is the first in the enum.
@pytest.mark.parametrize(
    ("no_claims", "wrong_type", "below", "limited", "expected"),
    [
        (True, True, True, True, SuppressionReason.VERIFICATION_FAILED),
        (False, True, True, True, SuppressionReason.CLAIMS_FILTERED_OUT),
        (False, False, True, True, SuppressionReason.BELOW_THRESHOLD),
        (False, False, False, True, SuppressionReason.RATE_LIMITED),
    ],
)
def test_the_first_applicable_reason_in_the_declared_order_wins(
    no_claims, wrong_type, below, limited, expected
):
    lens = CASUAL.model_copy(
        update={
            "allowed_claim_types": (ClaimType.DESCRIPTIVE,),
            "max_cards_per_10min": 1,
            "importance_threshold": 0.5,
        }
    )
    lens, shown = _limited(lens) if limited else (lens, ShownCards())
    claims = (
        []
        if no_claims
        else [_claim(ClaimType.COMPARATIVE if wrong_type else ClaimType.DESCRIPTIVE)]
    )
    moment = _moment(0.1 if below else 0.9)

    outcome = select(moment, claims, lens, shown)

    assert outcome.suppression_reason is expected
    assert outcome.claims == ()


def test_the_reasons_follow_the_enum_order():
    """The expectations above are only right if D14's order is what the enum declares."""
    order = list(SuppressionReason)
    assert order.index(SuppressionReason.VERIFICATION_FAILED) < order.index(
        SuppressionReason.CLAIMS_FILTERED_OUT
    )
    assert order.index(SuppressionReason.CLAIMS_FILTERED_OUT) < order.index(
        SuppressionReason.BELOW_THRESHOLD
    )
    assert order.index(SuppressionReason.BELOW_THRESHOLD) < order.index(
        SuppressionReason.RATE_LIMITED
    )


def test_casual_drops_comparative_claims_and_keeps_the_rest():
    claims = [_claim(ClaimType.COMPARATIVE, "cmp"), _claim(ClaimType.DESCRIPTIVE, "desc")]
    outcome = _select(_moment(0.9), CASUAL, claims)
    assert [c.claim_id for c in outcome.claims] == ["desc"]


def test_a_lens_that_drops_every_claim_is_claims_filtered_out_not_verification_failed():
    outcome = _select(_moment(0.9), CASUAL, [_claim(ClaimType.COMPARATIVE)])
    assert outcome.suppression_reason is SuppressionReason.CLAIMS_FILTERED_OUT


# --- the rate limit ------------------------------------------------------------------------------


def test_a_lens_at_its_limit_is_rate_limited_even_when_the_moment_clears_the_threshold():
    lens, shown = _limited(ANALYST.model_copy(update={"max_cards_per_10min": 2}))
    clears = _moment(0.9)
    assert clears.importance >= lens.importance_threshold
    assert (
        select(clears, [_claim()], lens, shown).suppression_reason is SuppressionReason.RATE_LIMITED
    )


def test_a_lens_at_its_limit_still_says_below_threshold_for_a_moment_that_misses_it():
    lens, shown = _limited(CASUAL.model_copy(update={"max_cards_per_10min": 1}))
    misses = _moment(CASUAL.importance_threshold / 2)
    assert (
        select(misses, [_claim()], lens, shown).suppression_reason
        is SuppressionReason.BELOW_THRESHOLD
    )


def test_the_window_rolls_on_the_match_clock():
    lens = ANALYST.model_copy(update={"max_cards_per_10min": 2})
    shown = ShownCards()

    def at(clock_ms: int) -> SuppressionReason | None:
        return select(_moment(0.9, clock_ms=clock_ms), [_claim()], lens, shown).suppression_reason

    assert at(0) is None
    assert at(MINUTE) is None
    assert at(2 * MINUTE) is SuppressionReason.RATE_LIMITED
    # A suppressed moment is not a card, so it did not use up any of the window.
    assert at(10 * MINUTE) is None  # the card at 0 has aged out, the one at 1 minute has not
    assert at(10 * MINUTE + 1) is SuppressionReason.RATE_LIMITED


def test_a_limit_of_zero_shows_nothing_but_a_breakthrough_type():
    lens = ANALYST.model_copy(update={"max_cards_per_10min": 0})
    assert _select(_moment(0.9), lens).suppression_reason is SuppressionReason.RATE_LIMITED
    goal = _moment(1.0, MomentType.GOAL)
    assert _select(goal, lens).suppression_reason is None


def test_a_breakthrough_type_is_never_rate_limited_but_still_counts():
    lens = ANALYST.model_copy(update={"max_cards_per_10min": 1})
    assert MomentType.GOAL in lens.breakthrough_types
    shown = ShownCards()
    full = select(_moment(0.9, clock_ms=0), [_claim()], lens, shown)
    assert full.suppression_reason is None
    goal = select(_moment(1.0, MomentType.GOAL, clock_ms=1), [_claim()], lens, shown)
    assert goal.suppression_reason is None
    # Two cards are now in the window against a limit of one.
    after = select(_moment(0.9, clock_ms=2), [_claim()], lens, shown)
    assert after.suppression_reason is SuppressionReason.RATE_LIMITED


def test_the_exemption_comes_from_the_lens_not_from_the_moment_type():
    lens = ANALYST.model_copy(update={"max_cards_per_10min": 0, "breakthrough_types": ()})
    goal = _moment(1.0, MomentType.GOAL)
    assert _select(goal, lens).suppression_reason is SuppressionReason.RATE_LIMITED


def test_two_matches_in_one_process_do_not_share_a_rate_limit():
    lens = ANALYST.model_copy(update={"max_cards_per_10min": 1})
    first, second = ShownCards(), ShownCards()
    assert select(_moment(0.9), [_claim()], lens, first).suppression_reason is None
    assert select(_moment(0.9), [_claim()], lens, first).suppression_reason is (
        SuppressionReason.RATE_LIMITED
    )
    # The same clock, a different match.
    assert select(_moment(0.9), [_claim()], lens, second).suppression_reason is None


def test_lenses_in_one_match_do_not_share_a_rate_limit():
    shown = ShownCards()
    one = ANALYST.model_copy(update={"lens_id": "one", "max_cards_per_10min": 1})
    other = ANALYST.model_copy(update={"lens_id": "other", "max_cards_per_10min": 1})
    assert select(_moment(0.9), [_claim()], one, shown).suppression_reason is None
    assert select(_moment(0.9), [_claim()], other, shown).suppression_reason is None


# --- scope is two code paths (D2) ----------------------------------------------------------------


def test_match_scope_judges_the_moment_as_it_is():
    assert _select(_moment(0.4), ANALYST).importance == 0.4
    assert _select(_moment(0.4, subject=OPPONENT), ANALYST).importance == 0.4


def test_team_scope_keeps_an_opponent_goal_and_raises_its_importance():
    moment = _moment(0.8, MomentType.GOAL, subject=OPPONENT)
    outcome = _select(moment, TEAM)
    assert outcome.suppression_reason is None
    assert outcome.importance == pytest.approx(min(1.0, 0.8 * settings.team_result_boost))
    assert outcome.importance > moment.importance


def test_team_scope_keeps_and_boosts_an_opponent_chance():
    moment = _moment(0.3, MomentType.CHANCE, subject=OPPONENT)
    outcome = _select(moment, TEAM)
    assert outcome.suppression_reason is None
    assert outcome.importance == pytest.approx(0.3 * settings.team_result_boost)


def test_a_boosted_importance_cannot_pass_one():
    assert _select(_moment(1.0, MomentType.GOAL, subject=OPPONENT), TEAM).importance == 1.0


def test_team_scope_drops_a_shift_by_the_focus_team_that_the_analyst_keeps():
    shift = _moment(0.35, subject=FOCUS)
    assert shift.importance >= TEAM.importance_threshold  # raw, it would clear the team threshold
    assert _select(shift, ANALYST).suppression_reason is None
    team = _select(shift, TEAM)
    assert team.importance == pytest.approx(0.35 * settings.team_focus_shift_damp)
    assert team.suppression_reason is SuppressionReason.BELOW_THRESHOLD


def test_team_scope_does_not_damp_a_shift_by_the_opponent():
    shift = _moment(0.35, subject=OPPONENT)
    outcome = _select(shift, TEAM)
    assert outcome.importance == 0.35
    assert outcome.suppression_reason is None


def test_the_focus_team_comes_from_the_lens():
    """Point the same lens at the other side and the same shift is damped the other way round."""
    other = TEAM.model_copy(update={"focus_team": OPPONENT.id})
    shift = _moment(0.35, subject=OPPONENT)
    assert _select(shift, other).importance == pytest.approx(0.35 * settings.team_focus_shift_damp)
    assert _select(_moment(0.35, subject=FOCUS), other).importance == 0.35


def test_player_scope_raises_rather_than_behaving_like_match():
    player = TEAM.model_copy(
        update={"scope": Scope.PLAYER, "focus_team": None, "focus_player": "p1"}
    )
    with pytest.raises(NotImplementedError):
        _select(_moment(0.9), player)


# --- a selection writes nothing and decides the same way twice -----------------------------------


def test_the_same_moments_and_lenses_make_the_same_selections():
    moments = [
        _moment(i / 10, [MomentType.GOAL, MomentType.CHANCE, MomentType.TACTICAL_SHIFT][i % 3],
                [FOCUS, OPPONENT][i % 2], clock_ms=i * 40_000, moment_id=f"m{i}")
        for i in range(10)
    ]  # fmt: skip

    def run() -> list[Selection]:
        shown = ShownCards()
        return [select(m, [_claim()], lens, shown) for m in moments for lens in lenses.all_lenses()]

    assert run() == run()


# --- no model, nothing agentic -------------------------------------------------------------------

FORBIDDEN = (
    "agent_framework",
    "azure",
    "openai",
    "anthropic",
    "matchlens.explanation",
    "matchlens.verification",
    "matchlens.rendering",
    "matchlens.ingest",
    "matchlens.source",
)


def test_importing_selection_loads_no_model_client_agent_or_frame_reader():
    code = (
        "import sys, matchlens.selection\n"
        f"bad = sorted(m for m in sys.modules"
        f" if any(m == f or m.startswith(f + '.') for f in {FORBIDDEN!r}))\n"
        "print(','.join(bad))\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == ""
