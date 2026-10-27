"""What a moment did to the match, read from its verified claims and nothing else.

The viewer is watching, so a card that says a goal was scored says nothing. What they cannot see
on the screen is what it meant: the side that was two down has levelled, the lead has been cut,
the siege has gone on for a fifth chance. That meaning is arithmetic on a claim already verified,
so it is not a new fact, and a state is only named when the claims it reads are there; otherwise
Rendering falls back to the template for the moment's type.

A goal is read from the score claim: the scorer's goals after the goal, and the other side's. A
descriptive count of the scorer's goals is the form Q26 2a gives a team whose opponent has none,
so the other side has none. Only a claim over the whole match up to the goal is the score; a
count over some other window is not.
"""

from collections.abc import Sequence

from matchlens.config import settings
from matchlens.models import Claim, Metric, Moment, RefKind

OPENER = "opener"  # the first goal of the match
TOOK_LEAD = "took_lead"  # level before, ahead now
EQUALISER = "equaliser"  # behind before, level now
EXTENDED = "extended"  # ahead before, further ahead now
PULLED_BACK = "pulled_back"  # behind before, still behind
RUN = "run"  # a run of big chances: the chance is one of several


def goal_state(moment: Moment, claims: Sequence[Claim]) -> str | None:
    """What the goal did to the score, or None if no claim holds the score it left."""
    scorer = moment.subject.id
    for claim in claims:
        first, *rest = claim.operands
        if first.metric is not Metric.GOALS or len(rest) > 1:
            continue
        if any(
            o.subject.kind is not RefKind.TEAM
            or o.metric is not Metric.GOALS
            or (o.window.start_ms, o.window.end_ms) != (0, moment.clock_ms)
            for o in claim.operands
        ):
            continue
        by_team = {o.subject.id: o.value for o in claim.operands}
        if scorer not in by_team:
            continue
        mine = by_team[scorer]
        theirs = next((v for team, v in by_team.items() if team != scorer), 0.0)
        return _goal_state(int(mine), int(theirs))
    return None


def _goal_state(mine: int, theirs: int) -> str:
    if theirs == 0:
        return OPENER if mine == 1 else EXTENDED
    if mine < theirs:
        return PULLED_BACK
    if mine == theirs:
        return EQUALISER
    return TOOK_LEAD if mine - theirs == 1 else EXTENDED


def chance_state(claims: Sequence[Claim]) -> str | None:
    """`run` when the chance is one of a run of big chances, else None."""
    for claim in claims:
        [first, *rest] = claim.operands
        if (
            first.metric is Metric.CHANCES
            and not rest
            and first.value >= settings.wording_chance_run
        ):
            return RUN
    return None
