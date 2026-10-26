"""What a goal or a chance did to the match, read from its claims, and how a card says it.

The viewer has seen the goal. A card earns its place by saying what it did: who is ahead now,
that it was level, that the siege goes on. Every state here is arithmetic on a verified score,
so each is tested on the score alone.
"""

import re

import pytest

from matchlens.models import (
    Claim,
    ClaimType,
    Depth,
    Metric,
    MomentType,
    Operand,
    Ref,
    RefKind,
    Window,
)
from matchlens.rendering import render, state, templates
from matchlens.spotting.importance import goal_magnitude
from tests.rendering.test_rendering import (
    ANALYST,
    CASUAL,
    NAMES,
    OPPONENT,
    SIDE,
    TEAM,
    _moment,
    _score,
    _selected,
)

CLOCK = 2_052_000


@pytest.mark.parametrize(
    ("mine", "theirs", "expected"),
    [
        (2, 0, state.EXTENDED),
        (1, 2, state.PULLED_BACK),
        (2, 2, state.EQUALISER),
        (3, 2, state.TOOK_LEAD),
        (3, 1, state.EXTENDED),
        (1, 3, state.PULLED_BACK),
    ],
)
def test_a_goal_is_read_from_the_score_it_leaves(mine, theirs, expected):
    claim = _score(SIDE, mine, OPPONENT, theirs)
    assert state.goal_state(_moment(MomentType.GOAL, SIDE), [claim]) == expected


def test_a_team_count_with_no_other_side_is_the_opener_when_it_is_one():
    def count(value: float) -> Claim:
        operand = Operand(
            subject=SIDE, metric=Metric.GOALS, window=Window(start_ms=0, end_ms=CLOCK),
            value=value, evidence_ids=(Ref(kind=RefKind.EVENT, id="ev"),),
        )  # fmt: skip
        return Claim(
            claim_id="count", moment_id="m", claim_type=ClaimType.DESCRIPTIVE,
            operands=(operand,), backing_reading=None, threshold=None, model="m", model_version="v",
        )  # fmt: skip

    goal = _moment(MomentType.GOAL, SIDE)
    assert state.goal_state(goal, [count(1)]) == state.OPENER
    assert state.goal_state(goal, [count(2)]) == state.EXTENDED


def test_no_score_no_state():
    assert state.goal_state(_moment(MomentType.GOAL), [_selected().claims[0]]) is None


def test_a_count_over_some_other_window_is_not_the_score():
    claim = _score(SIDE, 2, OPPONENT, 2)
    shifted = claim.model_copy(
        update={
            "operands": tuple(
                o.model_copy(update={"window": Window(start_ms=600_000, end_ms=CLOCK)})
                for o in claim.operands
            )
        }
    )
    assert state.goal_state(_moment(MomentType.GOAL, SIDE), [shifted]) is None


@pytest.mark.parametrize("lens", [CASUAL, TEAM, ANALYST], ids=lambda lens: lens.depth.value)
def test_a_goal_that_levels_it_is_headlined_by_what_it_did_not_that_it_happened(lens):
    selected = _selected(_score(SIDE, 2, OPPONENT, 2))
    rendition = render(_moment(MomentType.GOAL, SIDE), selected, lens, NAMES)
    assert rendition.headline is not None and re.search(
        r"level|equalise|draw", rendition.headline
    ), rendition.headline
    assert "scored" not in rendition.headline and "Goal" not in rendition.headline


def test_a_card_with_a_state_has_no_opening_line_and_no_time():
    selected = _selected(_score(SIDE, 2, OPPONENT, 1))
    for lens in (CASUAL, TEAM, ANALYST):
        rendition = render(_moment(MomentType.GOAL, SIDE), selected, lens, NAMES)
        assert rendition.body is not None
        assert not rendition.body.startswith(" ")
        assert not re.search(r"\b\d+:\d\d\b", f"{rendition.headline} {rendition.body}")


@pytest.mark.parametrize("depth", list(Depth))
@pytest.mark.parametrize("name", [state.OPENER, state.TOOK_LEAD, state.EQUALISER, state.EXTENDED])
def test_every_goal_state_has_a_headline_at_every_depth(name, depth):
    assert templates.state_headline("en", name, depth) is not None


@pytest.mark.parametrize("depth", list(Depth))
def test_every_state_has_a_headline_at_every_depth(depth):
    for name in (state.PULLED_BACK, state.RUN):
        assert templates.state_headline("en", name, depth) is not None


def test_a_side_lens_is_told_what_a_goal_did_to_its_own_side():
    """Ashworth went ahead of Larkfield, whom the lens follows: that is Larkfield falling behind,
    and it is said in the third person (D31)."""
    selected = _selected(_score(OPPONENT, 3, SIDE, 2))
    rendition = render(_moment(MomentType.GOAL, OPPONENT), selected, TEAM, NAMES)
    assert rendition.headline is not None and "Larkfield" in rendition.headline
    assert not re.search(r"\b(we|us|our)\b", rendition.headline, re.IGNORECASE)
    own = render(
        _moment(MomentType.GOAL, SIDE), _selected(_score(SIDE, 3, OPPONENT, 2)), TEAM, NAMES
    )
    assert own.headline is not None and "Larkfield" in own.headline
    assert own.headline != rendition.headline


@pytest.mark.parametrize(
    ("scored", "conceded", "expected"),
    [(1, 0, 1.0), (1, 1, 1.0), (2, 1, 1.0), (2, 0, 0.7), (1, 2, 0.7), (3, 0, 0.4), (4, 1, 0.4)],
)
def test_a_goals_magnitude_follows_what_it_did_to_the_score(scored, conceded, expected):
    assert goal_magnitude(scored, conceded) == pytest.approx(expected)
