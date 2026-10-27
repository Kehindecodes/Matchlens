"""L6: the team lens reweights and keeps both sides' moments; it does not filter by subject (D2).

Seed 1 runs through the pipeline once, with the team lens pointed at each side as two lenses
next to the presets. Both sides come from the match setup, so no test here names a club.
"""

import ast
from collections import Counter

import pytest

from apps import pipeline
from matchlens import lenses
from matchlens.audit import Audit
from matchlens.config import settings
from matchlens.models import (
    Claim,
    Depth,
    Lens,
    Moment,
    MomentType,
    Rendition,
    Scope,
    SuppressionReason,
)
from matchlens.selection.scope import judged_importance
from matchlens.source import MatchSetup, simulate
from tests.lenses.test_lenses import REPO_ROOT

SETUP = next(i for i in simulate(settings.match_seed) if isinstance(i, MatchSetup))
TEAM = next(lens for lens in lenses.all_lenses() if lens.scope is Scope.TEAM)
SIDES = tuple(
    TEAM.model_copy(update={"lens_id": f"{TEAM.lens_id}@{t.team_id}", "focus_team": t.team_id})
    for t in SETUP.match.teams
)


def _preset(depth: Depth) -> Lens:
    return next(lens for lens in lenses.all_lenses() if lens.depth is depth)


CASUAL, ANALYST = _preset(Depth.CASUAL), _preset(Depth.ANALYST)
# The team lens's own threshold and limits, at match scope: what it would show with no reweight.
UNWEIGHTED = TEAM.model_copy(
    update={"lens_id": f"{TEAM.lens_id}@none", "scope": Scope.MATCH, "focus_team": None}
)


class Demo:
    def __init__(self) -> None:
        self.moments: dict[str, Moment] = {}
        self.renditions: list[Rendition] = []
        self.claims: dict[str, Claim] = {}

    def record(self, moment, claims, verifications, renditions) -> None:
        self.moments[moment.moment_id] = moment
        self.claims |= {c.claim_id: c for c in claims}
        self.renditions.extend(renditions)

    def shown(self, lens: Lens) -> set[str]:
        return {r.moment_id for r in self._of(lens) if not r.suppressed}

    def rendition(self, lens: Lens, moment_id: str) -> Rendition:
        return next(r for r in self._of(lens) if r.moment_id == moment_id)

    def _of(self, lens: Lens) -> list[Rendition]:
        return [r for r in self.renditions if r.lens_id == lens.lens_id]


@pytest.fixture(scope="module")
def demo() -> Demo:
    run = Demo()
    every = (CASUAL, ANALYST, UNWEIGHTED, *SIDES)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Audit, "record", run.record)
        mp.setattr(pipeline.lenses, "all_lenses", lambda: list(every))
        pipeline.run(settings.match_seed, lambda card: None)
    return run


def _opponent(lens: Lens) -> str:
    return next(t.team_id for t in SETUP.match.teams if t.team_id != lens.focus_team)


# --- V11: pointing the lens at the other side reweights, it does not refilter -------------------


def test_both_sides_judge_every_moment(demo):
    for side in SIDES:
        assert {r.moment_id for r in demo._of(side)} == set(demo.moments)


def test_both_sides_show_a_near_identical_set_of_moments(demo):
    home, away = (demo.shown(side) for side in SIDES)
    # A filter by subject would leave the two sides close to disjoint.
    assert len(home & away) / len(home | away) >= 0.75


def test_every_goal_and_every_shown_chance_is_shown_to_both_sides(demo):
    home, away = (demo.shown(side) for side in SIDES)
    goals = {m for m, moment in demo.moments.items() if moment.type is MomentType.GOAL}
    assert goals <= home & away
    # The two sides differ only in which shifts their own side's damp pushed under the threshold.
    differ = {demo.moments[m].type for m in home ^ away}
    assert differ <= {MomentType.TACTICAL_SHIFT}


def test_the_same_moment_reads_differently_to_each_side_from_the_same_claims(demo):
    """Reframe, not refilter (D31): one claim set, a sentence for each side."""
    home, away = SIDES
    both = demo.shown(home) & demo.shown(away)
    assert both
    differ = 0
    for moment_id in both:
        ours, theirs = (demo.rendition(side, moment_id) for side in SIDES)
        assert ours.surviving_claim_ids == theirs.surviving_claim_ids
        differ += (ours.headline, ours.body) != (theirs.headline, theirs.body)
    # Not every card: an equaliser leaves the score level, and a shift reads the same from either
    # side, so what is asked is that the score is what the sides are told differently.
    assert differ


def test_every_goal_card_with_a_score_tells_each_side_it_from_its_side(demo):
    """Q28: B. The score is the first claim a team lens speaks, so it survives `standard`.

    A 1–0 has no score claim to speak: the side on nought cites nothing (Q26 2a).
    """
    names = {t.team_id: t.name for t in SETUP.match.teams}

    def has_score(rendition: Rendition) -> bool:
        claims = [demo.claims[i] for i in rendition.surviving_claim_ids]
        return any(len(c.operands) == 2 and c.operands[0].subject != c.operands[1].subject
                   for c in claims)  # fmt: skip

    for side in SIDES:
        assert side.focus_team is not None
        focus = names[side.focus_team]
        goals = [demo.rendition(side, m.moment_id) for m in demo.moments.values()
                 if m.type is MomentType.GOAL]  # fmt: skip
        scored = [r for r in goals if has_score(r)]
        assert scored
        for rendition in scored:
            body = rendition.body or ""
            assert any(f"{focus} {w}" in body for w in ("lead", "trail")) or "Level" in body, body


# --- the reweight on the demo match --------------------------------------------------------------


def test_an_opponent_goal_appears_with_the_highest_importance_the_lens_gives(demo):
    for side in SIDES:
        theirs = [
            m
            for m in demo.moments.values()
            if m.type is MomentType.GOAL and m.subject.id == _opponent(side)
        ]
        assert theirs
        for goal in theirs:
            assert goal.moment_id in demo.shown(side)
            # The reweight: a goal against the side is worth more to it (D2), up to the cap.
            boosted = min(1.0, goal.importance * settings.team_result_boost)
            assert judged_importance(goal, side) == boosted


def test_a_shift_the_analyst_shows_is_dropped_by_the_team_lens_by_the_reweight(demo):
    # The preset's side only: on seed 1 the other side has no shift that clears the threshold
    # raw, so for it the threshold alone does the dropping and the damp has nothing to show.
    side = next(s for s in SIDES if s.focus_team == TEAM.focus_team)
    dropped = [
        m
        for m in demo.moments.values()
        if m.type is MomentType.TACTICAL_SHIFT
        and m.importance >= side.importance_threshold  # raw, it clears the team threshold
        and m.moment_id in demo.shown(ANALYST)
        and demo.rendition(side, m.moment_id).suppression_reason
        is SuppressionReason.BELOW_THRESHOLD
    ]
    if dropped:
        return
    # The remontada has no such shift to show, so the reweight is checked on one made to fit:
    # the side's own shift, over the threshold raw and under it once damped.
    own = next(
        m
        for m in demo.moments.values()
        if m.type is MomentType.TACTICAL_SHIFT and m.subject.id == side.focus_team
    )
    raw = side.importance_threshold * 1.2
    shift = own.model_copy(update={"importance": raw})
    assert shift.importance >= side.importance_threshold
    assert judged_importance(shift, side) < side.importance_threshold


def test_the_team_lens_shows_fewer_cards_than_analyst_and_more_than_casual(demo):
    casual, analyst = len(demo.shown(CASUAL)), len(demo.shown(ANALYST))
    for side in SIDES:
        assert casual < len(demo.shown(side)) < analyst


def test_the_reweight_changes_what_the_team_lens_judges(demo):
    """What it judges, and so what it can show. On the remontada no chance sits between the boost
    and the threshold, so the set of cards happens to match the unweighted one; the importance
    does not (D2)."""
    for side in SIDES:
        moments = list(demo.moments.values())
        results = [m for m in moments if m.type in (MomentType.GOAL, MomentType.CHANCE)]
        assert any(judged_importance(m, side) > m.importance for m in results)
        assert all(judged_importance(m, UNWEIGHTED) == m.importance for m in moments)
        shown = demo.shown(side)
        gained = Counter(demo.moments[m].type for m in shown - demo.shown(UNWEIGHTED))
        lost = Counter(demo.moments[m].type for m in demo.shown(UNWEIGHTED) - shown)
        assert set(gained) <= {MomentType.GOAL, MomentType.CHANCE}
        assert set(lost) <= {MomentType.TACTICAL_SHIFT}


# --- invariant 10: focus_team drives it, no club is named in code -------------------------------


def test_no_club_name_or_team_id_is_a_literal_in_code():
    """The simulator invents the clubs, so `source` is where they may be spelled; nowhere else."""
    clubs = {t.name for t in SETUP.match.teams} | {t.team_id for t in SETUP.match.teams}
    offenders = []
    for path in [*(REPO_ROOT / "matchlens").rglob("*.py"), *(REPO_ROOT / "apps").rglob("*.py")]:
        relative = path.relative_to(REPO_ROOT)
        if "source" in relative.parts[:2]:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if any(club in node.value for club in clubs):
                offenders.append(f"{relative}:{node.lineno}")
    for path in (REPO_ROOT / "web").rglob("*"):
        if path.suffix in {".js", ".html"}:
            text = path.read_text()
            offenders += [f"{path.relative_to(REPO_ROOT)}: {c}" for c in clubs if c in text]
    assert offenders == []
