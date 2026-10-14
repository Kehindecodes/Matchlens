from matchlens.models import Frame, Phase
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


def test_without_the_score_fold_every_score_is_zero():
    state = MatchStateTracker(_setup()).observe(_frame(0, 0))
    assert state is not None
    assert [t.goals for t in state.score] == [0, 0]


def test_the_score_comes_from_the_fold_it_is_given():
    setup = _setup()
    home = next(t for t in setup.match.teams if t.is_home)
    state = MatchStateTracker(setup, score=lambda clock: {home.team_id: 2}).observe(_frame(0, 0))
    assert state is not None
    assert [t.goals for t in state.score] == [2, 0]
