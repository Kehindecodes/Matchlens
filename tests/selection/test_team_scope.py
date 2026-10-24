"""L6: the team lens reweights and keeps both sides' moments; it does not filter by subject (D2).

Seed 1 runs through the pipeline once, with the team lens pointed at each side as two lenses
next to the presets. Both sides come from the match setup, so no test here names a club. The
framing half is blocked on O3, so the one test that needs it is a strict xfail.
"""

import ast
from collections import Counter

import pytest

from apps import pipeline
from matchlens import lenses
from matchlens.config import settings
from matchlens.models import Depth, Lens, Moment, MomentType, Rendition, Scope, SuppressionReason
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

    def record(self, moment, claims, verifications, renditions) -> None:
        self.moments[moment.moment_id] = moment
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
        mp.setattr(pipeline.audit, "record", run.record)
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


@pytest.mark.xfail(strict=True, reason="the framing half is blocked on O3 (L6)")
def test_the_same_moment_reads_differently_to_each_side(demo):
    home, away = SIDES
    for moment_id in demo.shown(home) & demo.shown(away):
        texts = {(demo.rendition(s, moment_id).headline, demo.rendition(s, moment_id).body)
                 for s in SIDES}  # fmt: skip
        assert len(texts) == 2


# --- the reweight on the demo match --------------------------------------------------------------


def test_an_opponent_goal_appears_with_the_highest_importance_the_lens_gives(demo):
    for side in SIDES:
        theirs = [
            m
            for m in demo.moments.values()
            if m.type is MomentType.GOAL and m.subject.id == _opponent(side)
        ]
        assert theirs
        top = max(judged_importance(m, side) for m in demo.moments.values())
        for goal in theirs:
            assert goal.moment_id in demo.shown(side)
            assert judged_importance(goal, side) == top


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
    assert dropped


def test_the_team_lens_shows_fewer_cards_than_analyst_and_more_than_casual(demo):
    casual, analyst = len(demo.shown(CASUAL)), len(demo.shown(ANALYST))
    for side in SIDES:
        assert casual < len(demo.shown(side)) < analyst


def test_the_reweight_changes_what_the_team_lens_shows(demo):
    """With the same threshold and limits at match scope, the cards are not the same ones."""
    unweighted = demo.shown(UNWEIGHTED)
    for side in SIDES:
        shown = demo.shown(side)
        assert shown != unweighted
        gained = Counter(demo.moments[m].type for m in shown - unweighted)
        lost = Counter(demo.moments[m].type for m in unweighted - shown)
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
            text = node.value if isinstance(node, ast.Constant) else None
            if isinstance(text, str) and any(club in text for club in clubs):
                offenders.append(f"{relative}:{node.lineno}")
    for path in (REPO_ROOT / "web").rglob("*"):
        if path.suffix in {".js", ".html"}:
            text = path.read_text()
            offenders += [f"{path.relative_to(REPO_ROOT)}: {c}" for c in clubs if c in text]
    assert offenders == []
