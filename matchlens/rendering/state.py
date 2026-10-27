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
from dataclasses import dataclass

from matchlens.config import settings
from matchlens.models import Claim, Metric, Moment, RefKind

OPENER = "opener"  # the first goal of the match
TOOK_LEAD = "took_lead"  # level before, ahead now
EQUALISER = "equaliser"  # behind before, level now
EXTENDED = "extended"  # ahead before, further ahead now
PULLED_BACK = "pulled_back"  # behind before, still behind
RUN = "run"  # a run of big chances: the chance is one of several
LEAD_CANCELLED = "lead_cancelled"  # a goal ruled out that had put its side ahead
EQUALISER_CANCELLED = "equaliser_cancelled"  # a goal ruled out that had levelled it


@dataclass(frozen=True)
class Score:
    """The score a moment left, read from the claim that holds it, from the moment's side."""

    claim: Claim
    mine: int  # the goals of the moment's subject: the scorer, or the side whose goal went
    theirs: int
    other: str | None  # the other side's team id, where the claim names it: it has scored


def score(moment: Moment, claims: Sequence[Claim]) -> Score | None:
    """The score over the whole match up to the moment, or None if no claim holds it.

    A goal's and a ruled-out goal's claims both carry it. A count of one side alone is the
    form a side whose opponent has none gets (Q26 2a), so the side it does not count has none:
    after a ruled-out goal, that may be the moment's own side.
    """
    if moment.subject.kind is not RefKind.TEAM:
        return None
    side = moment.subject.id
    for claim in claims:
        first, *rest = claim.operands
        if first.metric is not Metric.GOALS or len(rest) > 1:
            continue
        if any(
            operand.subject.kind is not RefKind.TEAM
            or operand.metric is not Metric.GOALS
            or (operand.window.start_ms, operand.window.end_ms) != (0, moment.clock_ms)
            for operand in claim.operands
        ):
            continue
        by_team = {operand.subject.id: operand.value for operand in claim.operands}
        others = [team for team in by_team if team != side]
        if side not in by_team and len(others) != 1:
            continue
        other = others[0] if others else None
        theirs = 0 if other is None else int(by_team[other])
        return Score(claim, int(by_team.get(side, 0)), theirs, other)
    return None


def goal_state(moment: Moment, claims: Sequence[Claim]) -> str | None:
    """What the goal did to the score, or None if no claim holds the score it left."""
    left = score(moment, claims)
    return None if left is None else _goal_state(left.mine, left.theirs)


def disallowed_state(moment: Moment, claims: Sequence[Claim]) -> str | None:
    """What the ruled-out goal would have done, read from the score after it went.

    Level now: it had put its side ahead. One behind now: it had levelled. Anything else, or no
    score claim, names no state.
    """
    left = score(moment, claims)
    if left is None:
        return None
    if left.mine == left.theirs:
        return LEAD_CANCELLED
    if left.mine + 1 == left.theirs:
        return EQUALISER_CANCELLED
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
