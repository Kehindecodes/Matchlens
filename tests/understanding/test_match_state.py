from matchlens.models import Event, Frame, Outcome, Phase
from matchlens.source import MatchSetup, simulate
from matchlens.understanding.match_state import MatchStateTracker


def _setup() -> MatchSetup:
    setup = next(iter(simulate(1)))
    assert isinstance(setup, MatchSetup)
    return setup


def _frame(seq: int, clock_ms: int, period: int = 1) -> Frame:
    return Frame(
        seq=seq, clock_ms=clock_ms, period=period, phase=Phase.IN_PLAY, ball_x=0.0, ball_y=0.0,
        ball_z=0.0, ball_speed=0.0, carrier=None, players=(),
    )  # fmt: skip


def test_one_state_per_new_match_second():
    tracker = MatchStateTracker(_setup())
    clocks = [0, 400, 999, 1_000, 1_500, 3_200]
    states = [tracker.observe(_frame(i, c)) for i, c in enumerate(clocks)]
    assert [s.clock_ms if s else None for s in states] == [0, None, None, 1_000, None, 3_200]


def test_a_state_carries_the_seq_and_period_of_its_item():
    state = MatchStateTracker(_setup()).observe(_frame(42, 2_900_000, period=2))
    assert state is not None
    assert (state.seq, state.period) == (42, 2)


def test_home_is_listed_first():
    setup = _setup()
    home = next(t for t in setup.match.teams if t.is_home)
    state = MatchStateTracker(setup).observe(_frame(0, 0))
    assert state is not None
    assert state.score[0].team_id == home.team_id


def test_before_any_goal_every_score_is_zero():
    state = MatchStateTracker(_setup()).observe(_frame(0, 0))
    assert state is not None
    assert [team.goals for team in state.score] == [0, 0]


def _goal(event: Event, clock_ms: int, seq: int) -> Event:
    return event.model_copy(update={"clock_ms": clock_ms, "seq": seq})


def test_a_goal_changes_the_score_at_once_even_within_a_second():
    setup = _setup()
    home = next(team for team in setup.match.teams if team.is_home)
    tracker = MatchStateTracker(setup)
    goal = next(
        item
        for item in simulate(1)
        if isinstance(item, Event) and item.outcome is Outcome.GOAL and item.team == home.team_id
    )
    assert tracker.observe(_frame(0, 5_000)) is not None
    state = tracker.observe(_goal(goal, 5_400, seq=1))
    assert state is not None
    assert [team.goals for team in state.score] == [1, 0]
    assert tracker.observe(_frame(2, 5_800)) is None  # the second's state is already out


def test_the_scoreboard_ends_on_the_seeded_matchs_final_score():
    items = list(simulate(1))
    setup = items[0]
    assert isinstance(setup, MatchSetup)
    tracker = MatchStateTracker(setup)
    states = [state for item in items[1:] if (state := tracker.observe(item)) is not None]
    goals = [item for item in items if isinstance(item, Event) and item.outcome is Outcome.GOAL]
    assert goals
    final = {team.team_id: team.goals for team in states[-1].score}
    assert final == {
        team.team_id: sum(goal.team == team.team_id for goal in goals) for team in setup.match.teams
    }
