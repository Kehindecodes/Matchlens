"""U1: possessions sequenced from the event log, checked against seed 1's frames and events."""

from statistics import mean

import pytest
from pydantic import ValidationError

from matchlens.ingest import Ingest
from matchlens.models import Action, Event, Outcome, Phase, Possession, PossessionOutcome, Zone
from matchlens.source import simulate
from matchlens.understanding.possession import sequence
from tests.source.helpers import Played, split


def _possessions(played: Played) -> list[Possession]:
    ingest = Ingest()
    for item in played.items:
        ingest.accept(item)
    return sequence(ingest.record(), 0, played.end_clock_ms + 1)


@pytest.fixture(scope="module")
def played() -> Played:
    return split(list(simulate(1)))


@pytest.fixture(scope="module")
def possessions(played: Played) -> list[Possession]:
    return _possessions(played)


@pytest.fixture(scope="module")
def by_id(played: Played) -> dict[str, Event]:
    return {e.event_id: e for e in played.events}


def test_a_possession_is_more_than_two_events_on_average(possessions):
    assert mean(len(p.event_ids) for p in possessions) > 2


def test_no_possession_spans_stopped_time(played, possessions, by_id):
    phase = {f.seq: f.phase for f in played.frames}
    for p in possessions:
        first, last = by_id[p.event_ids[0]].frame_ref, by_id[p.event_ids[-1]].frame_ref
        stopped = [s for s in range(first, last + 1) if phase.get(s) is Phase.STOPPED]
        assert not stopped, f"{p.possession_id} spans stopped frames {stopped[:3]}"


def test_possessions_are_in_clock_order_and_never_overlap(possessions):
    for before, after in zip(possessions, possessions[1:], strict=False):
        assert before.end_clock_ms <= after.start_clock_ms


def test_possessions_cover_the_in_play_time(played, possessions):
    """Q13: what is left is the ball in flight, which belongs to no team."""
    interval = played.frames[1].clock_ms - played.frames[0].clock_ms
    in_play = interval * sum(f.phase is Phase.IN_PLAY for f in played.frames)
    covered = sum(p.end_clock_ms - p.start_clock_ms for p in possessions)
    assert covered >= 0.85 * in_play


def test_the_ball_is_won_back_within_three_seconds_of_a_turnover(possessions):
    for lost, won in zip(possessions, possessions[1:], strict=False):
        if lost.outcome is PossessionOutcome.TURNOVER:
            assert won.start_clock_ms - lost.end_clock_ms <= 3_000, lost.possession_id


def test_pass_count_recomputes_from_the_cited_events_alone(possessions, by_id):
    for p in possessions:
        recount = sum(by_id[i].action is Action.PASS for i in p.event_ids)
        assert recount == p.pass_count, p.possession_id


def test_a_possession_ending_in_a_shot_has_outcome_shot(possessions, by_id):
    ended_in_a_shot = [p for p in possessions if by_id[p.event_ids[-1]].action is Action.SHOT]
    assert any(by_id[p.event_ids[-1]].outcome is Outcome.GOAL for p in ended_in_a_shot)
    assert all(p.outcome is PossessionOutcome.SHOT for p in ended_in_a_shot)


def test_a_restart_starts_a_possession(played, possessions, by_id):
    """Q10: throw-ins, free kicks, corners and goal kicks open a possession, not the pass after."""
    restarts = {Action.THROW_IN, Action.FREE_KICK, Action.CORNER, Action.GOAL_KICK}
    firsts = {p.event_ids[0] for p in possessions}
    taken = [e.event_id for e in played.events if e.action in restarts]
    assert taken and all(i in firsts for i in taken)


def test_the_foul_is_the_last_event_of_the_fouled_teams_possession(possessions, by_id):
    """Q11: the foul is the other team's event, and still the one this possession cites."""
    fouled = [p for p in possessions if p.outcome is PossessionOutcome.FOUL]
    assert fouled
    for p in fouled:
        foul = by_id[p.event_ids[-1]]
        assert foul.action is Action.FOUL
        assert foul.team != p.team
        assert all(by_id[i].team == p.team for i in p.event_ids[:-1])


def test_the_half_ending_during_a_possession_ends_it(possessions, by_id):
    """Q12: both halves of seed 1 end with the ball live."""
    ended = [p for p in possessions if p.outcome is PossessionOutcome.PERIOD_END]
    assert len(ended) == 2
    assert all(by_id[p.event_ids[-1]].action is Action.PERIOD_END for p in ended)


def test_cards_and_substitutions_are_in_no_possession(played, possessions):
    cited = {i for p in possessions for i in p.event_ids}
    roster = {Action.SUBSTITUTION, Action.YELLOW_CARD, Action.RED_CARD}
    assert not [e for e in played.events if e.action in roster and e.event_id in cited]


def test_out_of_play_and_turnover_follow_from_the_events(possessions, by_id):
    """Out of play: the last event went out, or a throw-in, corner or goal kick came next."""
    restarts = {Action.THROW_IN, Action.CORNER, Action.GOAL_KICK}
    for p, after in zip(possessions, possessions[1:], strict=False):
        last, next_first = by_id[p.event_ids[-1]], by_id[after.event_ids[0]]
        if p.outcome is PossessionOutcome.OUT_OF_PLAY:
            assert last.outcome is Outcome.OUT_OF_PLAY or next_first.action in restarts
        elif p.outcome is PossessionOutcome.TURNOVER:
            assert next_first.team != p.team and next_first.action not in restarts


def test_zones_are_from_the_attacking_teams_view(possessions, by_id):
    """A shot is taken in the attacking team's own final third, whichever way it is kicking."""
    shots = [p for p in possessions if p.outcome is PossessionOutcome.SHOT]
    final = [p for p in shots if p.end_zone is Zone.FINAL_THIRD]
    assert len(final) > 0.8 * len(shots)


def test_a_window_leaves_out_the_possession_still_going_at_its_end(played, possessions):
    """Its outcome is not known yet; it appears once the event that ends it is in the window."""
    ingest = Ingest()
    for item in played.items:
        ingest.accept(item)
    cut = 30 * 60_000
    early = sequence(ingest.record(), 0, cut)
    assert early == possessions[: len(early)]
    assert possessions[len(early)].end_clock_ms >= cut or (
        possessions[len(early) + 1].start_clock_ms >= cut
    )


def test_a_possession_needs_at_least_one_event():
    with pytest.raises(ValidationError):
        Possession(
            possession_id="p", team="t", start_clock_ms=0, end_clock_ms=0, pass_count=0,
            start_zone=Zone.MIDDLE_THIRD, end_zone=Zone.MIDDLE_THIRD,
            outcome=PossessionOutcome.TURNOVER, event_ids=(),
        )  # fmt: skip


def test_the_same_seed_gives_the_same_possessions_byte_for_byte(possessions):
    again = _possessions(split(list(simulate(1))))
    assert [p.model_dump_json() for p in again] == [p.model_dump_json() for p in possessions]
