"""R2: four archetypes that drive recognisably different matches.

The multi-seed checks simulate a dozen matches and are marked `slow`: the default run skips them
and CI runs them in their own job (`pytest -m slow`).
"""

import ast
import hashlib
import itertools
import statistics
from dataclasses import dataclass
from pathlib import Path

import pytest

from matchlens.models import Action, Outcome, Phase, Signal
from matchlens.source.archetypes import ARCHETYPES, COMEBACK, ONE_SIDED, interpolate
from matchlens.source.simulator import simulate
from matchlens.understanding.epochs import detect
from matchlens.understanding.possession import sequence
from matchlens.understanding.signals import cadence, measure
from tests.source.helpers import Played, played, reader, split

REPO_ROOT = Path(__file__).resolve().parents[2]
SEEDS = (1, 2, 3)
METRICS = ("shots", "home_pass_share", "goals", "fouls")


@dataclass(frozen=True)
class Summary:
    shots: int
    home_pass_share: float
    goals: int
    fouls: int
    home_goals: int
    away_goals: int
    possession_length: float
    events: int
    in_play_min: float


def _summary(match: Played) -> Summary:
    home = match.setup.match.teams[0].team_id
    passes = [e for e in match.events if e.action is Action.PASS]
    goals = [e for e in match.events if e.outcome is Outcome.GOAL]
    possessions = sequence(reader(match), 0, match.end_clock_ms + 1)
    interval = match.frames[1].clock_ms - match.frames[0].clock_ms
    return Summary(
        shots=sum(e.action is Action.SHOT for e in match.events),
        home_pass_share=sum(e.team == home for e in passes) / len(passes),
        goals=len(goals),
        fouls=sum(e.action is Action.FOUL for e in match.events),
        home_goals=sum(e.team == home for e in goals),
        away_goals=sum(e.team != home for e in goals),
        possession_length=statistics.mean(len(p.event_ids) for p in possessions),
        events=len(match.events),
        in_play_min=interval * sum(f.phase is Phase.IN_PLAY for f in match.frames) / 60_000,
    )


def test_four_archetypes_with_schedules_covering_the_whole_clock():
    assert set(ARCHETYPES) == {"comeback", "one_sided", "tight", "scrappy"}
    for a in ARCHETYPES.values():
        for schedule in (a.momentum, a.home_press, a.away_press):
            assert schedule[0][0] <= 0 and schedule[-1][0] >= 100, a.archetype_id
            assert [m for m, _ in schedule] == sorted(m for m, _ in schedule)
        assert all(-1 <= interpolate(a.momentum, m) <= 1 for m in range(101))


def test_the_comeback_is_untouched():
    """The demo video and the committed demo seed depend on it."""
    assert COMEBACK.goals[0].minute == 18 and COMEBACK.red_cards[0].minute == 63.0
    assert ARCHETYPES["comeback"] is COMEBACK


def test_the_comeback_is_byte_identical_to_before_retention():
    """Q16: retention defaults to 0 and leaves the comeback exactly as `generator-2` plays it."""
    digest = hashlib.sha256()
    for item in played("comeback", 1).items:
        digest.update(item.model_dump_json().encode())
    assert digest.hexdigest()[:16] == "828b8ea241c7d585"


def test_retention_gives_the_one_sided_match_real_possession_dominance():
    match = played(ONE_SIDED.archetype_id, 1)
    home = match.setup.match.teams[0].team_id
    passes = [e for e in match.events if e.action is Action.PASS]
    assert sum(e.team == home for e in passes) / len(passes) > 0.55


def test_nothing_downstream_of_match_source_reads_the_archetype():
    """D25: archetype and seed are provenance; a real feed has neither."""
    offenders = []
    for root in ("matchlens", "apps"):
        for path in (REPO_ROOT / root).rglob("*.py"):
            if path.relative_to(REPO_ROOT).parts[:2] == ("matchlens", "source"):
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or "", *(a.name for a in node.names)]
                if any("archetype" in n for n in names) or (
                    isinstance(node, ast.Attribute) and node.attr in ("archetype_id", "seed")
                ):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{getattr(node, 'lineno', 0)}")
    assert offenders == []


# --- across seeds: slow ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def summaries() -> dict[str, list[Summary]]:
    return {a: [_summary(played(a, s)) for s in SEEDS] for a in ARCHETYPES}


@pytest.mark.slow
def test_every_pair_of_archetypes_separates_beyond_seed_variance(summaries):
    """For each pair, some metric's means differ by more than both seed spreads together."""
    for a, b in itertools.combinations(summaries, 2):
        gaps = {}
        for metric in METRICS:
            xa = [getattr(s, metric) for s in summaries[a]]
            xb = [getattr(s, metric) for s in summaries[b]]
            spread = statistics.stdev(xa) + statistics.stdev(xb)
            gaps[metric] = abs(statistics.mean(xa) - statistics.mean(xb)) - spread
        assert max(gaps.values()) > 0, f"{a} vs {b} do not separate: {gaps}"


def _press_possession_r(match: Played, team: str) -> float:
    r = reader(match)
    rows = [m for c, e in cadence(detect(r), match.end_clock_ms) for m in measure(r, e, c)]

    def series(signal: Signal) -> list[float]:
        return [m.value for m in rows if m.signal is signal and m.team == team]

    return statistics.correlation(
        series(Signal.POSSESSION_CONTROL), series(Signal.PRESSING_INTENSITY)
    )


@pytest.mark.slow
@pytest.mark.parametrize("archetype", sorted(ARCHETYPES))
def test_pressing_does_not_simply_track_possession(archetype):
    """Q17: in every archetype, the two correlate weakly for both teams, averaged over seeds.

    Per archetype, not per match: one match can run strong on its own (tight, seed 1, home:
    r = -0.70, against -0.29 on seeds 2 and 3), and the claim is about how the archetype plays.
    """
    for side in (0, 1):
        rs = []
        for seed in SEEDS:
            match = played(archetype, seed)
            rs.append(_press_possession_r(match, match.setup.match.teams[side].team_id))
        assert abs(statistics.mean(rs)) < 0.6, f"{archetype} side {side}: r = {rs}"


@pytest.mark.slow
def test_each_archetype_has_its_own_final_score_shape(summaries):
    for s in summaries["comeback"]:
        assert s.home_goals > s.away_goals >= 1  # behind, then won
    for s in summaries["one_sided"]:
        assert s.home_goals >= 2 and s.away_goals == 0
    for s in summaries["tight"]:
        assert s.goals <= 1
    for s in summaries["scrappy"]:
        assert s.home_goals >= 1 and s.away_goals >= 1


@pytest.mark.slow
def test_scrappy_possessions_are_much_shorter_than_tight_ones(summaries):
    scrappy = statistics.mean(s.possession_length for s in summaries["scrappy"])
    tight = statistics.mean(s.possession_length for s in summaries["tight"])
    assert scrappy < 0.85 * tight, f"scrappy {scrappy:.2f} vs tight {tight:.2f}"


@pytest.mark.slow
def test_every_archetype_plays_a_plausible_match(summaries):
    for archetype, rows in summaries.items():
        for s in rows:
            assert 1_500 <= s.events <= 2_200, (archetype, s.events)
            assert 50 <= s.in_play_min <= 66, (archetype, s.in_play_min)


@pytest.mark.slow
@pytest.mark.parametrize("archetype", sorted(ARCHETYPES))
def test_every_archetype_is_deterministic(archetype):
    again = split(list(simulate(1, ARCHETYPES[archetype])))
    first = played(archetype, 1)
    assert [i.model_dump_json() for i in again.items] == [i.model_dump_json() for i in first.items]
