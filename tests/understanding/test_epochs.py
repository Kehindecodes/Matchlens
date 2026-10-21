"""U5: epochs at every structural break, with score and player counts derived from the log."""

import pytest

from matchlens.ingest import Ingest, RecordReader
from matchlens.ingest.events import InMemoryEventRepository
from matchlens.models import Action, EpochTrigger, Event, Outcome
from matchlens.understanding import epochs
from matchlens.understanding.epochs import detect
from tests.source.helpers import Played


def _reader(played: Played, events: list[Event] | None = None) -> RecordReader:
    if events is None:
        ingest = Ingest()
        for item in played.items:
            ingest.accept(item)
        return ingest.record()
    repository = InMemoryEventRepository()
    for event in events:
        repository.append(event)
    return RecordReader(played.setup, repository)


@pytest.fixture(scope="module")
def detected(played):
    return detect(_reader(played))


def _inserted(played: Played, extra: Event, after: Event) -> list[Event]:
    """The log with `extra` straight after `after`, renumbered so `seq` stays in order."""
    i = played.events.index(after) + 1
    events = [*played.events[:i], extra, *played.events[i:]]
    return [e.model_copy(update={"seq": n}) for n, e in enumerate(events)]


def _goals(played: Played) -> list[Event]:
    return [e for e in played.events if e.outcome is Outcome.GOAL]


def test_three_goals_a_red_card_and_half_time_make_six_epochs(played, detected):
    assert len(_goals(played)) == 3
    assert sum(e.action is Action.RED_CARD for e in played.events) == 1
    breaks = sorted(
        [(e.clock_ms, EpochTrigger.GOAL) for e in _goals(played)]
        + [(e.clock_ms, EpochTrigger.RED_CARD) for e in played.events
           if e.action is Action.RED_CARD]
        + [(e.clock_ms, EpochTrigger.HALF_TIME) for e in played.events
           if e.action is Action.PERIOD_START and e.period > 1]
    )  # fmt: skip
    assert [e.trigger for e in detected] == [None, *(t for _, t in breaks)]
    assert [e.start_clock_ms for e in detected[1:]] == [c for c, _ in breaks]


def test_the_score_at_each_epoch_counts_the_goals_up_to_its_start(played, detected):
    """A goal epoch's score includes the goal that started it (Q14)."""
    for epoch in detected:
        counted = {t.team_id: 0 for t in played.setup.match.teams}
        for goal in _goals(played):
            if goal.clock_ms <= epoch.start_clock_ms:
                assert goal.team is not None
                counted[goal.team] += 1
        assert epoch.score_state == counted, epoch.epoch_id


def test_a_red_card_drops_the_count_and_substitutions_do_not(played, detected):
    [red] = [e for e in played.events if e.action is Action.RED_CARD]
    subs = [e for e in played.events if e.action is Action.SUBSTITUTION]
    assert subs  # seed 1 makes substitutions, so a missed one would show here
    before = next(e for e in reversed(detected) if e.start_clock_ms < red.clock_ms)
    after = next(e for e in detected if e.trigger is EpochTrigger.RED_CARD)
    assert red.team is not None
    assert after.player_counts[red.team] == before.player_counts[red.team] - 1
    assert detected[0].player_counts == {t.team_id: 11 for t in played.setup.match.teams}
    assert all(sum(e.player_counts.values()) >= 21 for e in detected)  # only the one red


def test_a_double_substitution_leaves_the_counts_alone(played):
    sub = next(e for e in played.events if e.action is Action.SUBSTITUTION)
    second = sub.model_copy(update={"event_id": "extra-sub"})
    assert detect(_reader(played, _inserted(played, second, after=sub))) == detect(_reader(played))


def test_epochs_are_contiguous_and_never_overlap(played, detected):
    kickoff = next(e for e in played.events if e.action is Action.PERIOD_START)
    assert detected[0].start_clock_ms == kickoff.clock_ms
    starts = [e.start_clock_ms for e in detected]
    assert starts == sorted(set(starts))  # strictly increasing: each clock in exactly one


def test_only_the_opening_epoch_has_no_trigger(detected):
    assert detected[0].trigger is None
    assert all(e.trigger is not None for e in detected[1:])


def test_yellow_cards_and_added_time_are_not_breaks(played, detected):
    quiet = {Action.YELLOW_CARD, Action.ADDED_TIME_ANNOUNCED, Action.SUBSTITUTION}
    clocks = {e.clock_ms for e in played.events if e.action in quiet}
    breaks = {e.start_clock_ms for e in detected[1:]}
    assert clocks and not (clocks & breaks)


def test_two_goals_at_the_same_clock_make_one_boundary_counting_both(played):
    """Deliberately one: two boundaries at one clock would make an epoch no clock is in."""
    first = _goals(played)[0]
    other_team = next(t.team_id for t in played.setup.match.teams if t.team_id != first.team)
    scorer = next(e for e in played.events if e.team == other_team and e.action is Action.SHOT)
    second = scorer.model_copy(
        update={"event_id": "same-clock-goal", "clock_ms": first.clock_ms, "outcome": Outcome.GOAL}
    )
    found = detect(_reader(played, _inserted(played, second, after=first)))
    at = [e for e in found if e.start_clock_ms == first.clock_ms]
    assert len(at) == 1 and at[0].trigger is EpochTrigger.GOAL
    assert at[0].score_state[other_team] == 1 and sum(at[0].score_state.values()) == 2


def test_detecting_twice_gives_identical_epochs_and_the_module_holds_no_state(played, detected):
    assert detect(_reader(played)) == detected
    mutable = {
        name for name, value in vars(epochs).items()
        if not name.startswith("__") and isinstance(value, dict | list | set)
    }  # fmt: skip
    assert not mutable


def test_a_partial_log_gives_a_prefix_of_the_full_epochs(played, detected):
    """Epochs only append as the log grows, so early ones never change (invariant 2)."""
    cut = detected[3].start_clock_ms
    early = detect(_reader(played, [e for e in played.events if e.clock_ms < cut]))
    assert early == detected[:3]
