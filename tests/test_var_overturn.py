"""Q49: a goal VAR rules out, on the remontada demo. Scored at 84', overturned for offside.

The goal event is never edited (invariant 2, D4): the overturn is a new event, and the score,
the epochs, the claims and the cards are all recomputed from the log with it.
"""

import pytest
from pydantic import ValidationError

from apps.pipeline import Pipeline
from matchlens import explanation, verification
from matchlens.ingest import FrozenLog, Ingest
from matchlens.models import (
    Action,
    EpochTrigger,
    Event,
    Metric,
    MomentType,
    Outcome,
    VarReason,
    Verdict,
    standing_goals,
)
from matchlens.rendering import Card
from matchlens.source import MatchSetup, simulate
from matchlens.spotting import Spotter
from matchlens.understanding import Movement, Understanding
from matchlens.understanding.match_state import MatchStateTracker
from tests.source.helpers import Played, split


@pytest.fixture(scope="module")
def demo() -> Played:
    return split(list(simulate(1)))


@pytest.fixture(scope="module")
def overturn(demo: Played) -> Event:
    [event] = [e for e in demo.events if e.action is Action.VAR_OVERTURNED]
    return event


@pytest.fixture(scope="module")
def cards(demo: Played) -> list[Card]:
    pipeline = Pipeline()
    try:
        return [card for item in demo.items for card in pipeline.process(item)]
    finally:
        pipeline.close()


def _goal(demo: Played, event_id: str | None) -> Event:
    return next(e for e in demo.events if e.event_id == event_id)


def test_the_demo_rules_out_a_home_goal_for_offside_and_still_ends_3_2(demo, overturn):
    goal = _goal(demo, overturn.overturns)
    home = next(t.team_id for t in demo.setup.match.teams if t.is_home)
    assert goal.outcome is Outcome.GOAL and goal.team == overturn.team == home
    assert goal.player == overturn.player
    assert overturn.var_reason is VarReason.OFFSIDE
    assert 84 * 60_000 <= goal.clock_ms < overturn.clock_ms < 89 * 60_000
    final = standing_goals(demo.events)
    assert sum(e.team == home for e in final) == 3 and len(final) == 5


def test_the_goal_event_is_left_as_it_was(demo, overturn):
    # Invariant 2: the correction is a new event; the goal still says it went in.
    assert _goal(demo, overturn.overturns).outcome is Outcome.GOAL
    assert overturn.seq > _goal(demo, overturn.overturns).seq


def test_an_overturn_needs_the_goal_and_the_reason_and_nothing_else_carries_them(overturn):
    with pytest.raises(ValidationError, match="needs overturns and var_reason"):
        Event.model_validate(overturn.model_dump() | {"var_reason": None})
    goal_fields = overturn.model_dump() | {"action": Action.YELLOW_CARD}
    with pytest.raises(ValidationError, match="only for var_overturned"):
        Event.model_validate(goal_fields)


def test_the_scoreboard_counts_the_goal_until_the_overturn_and_not_after(demo, overturn):
    goal = _goal(demo, overturn.overturns)
    tracker = MatchStateTracker(demo.setup)
    at: dict[str, tuple[int, int]] = {}
    for item in demo.items:
        if isinstance(item, MatchSetup):
            continue
        state = tracker.observe(item)
        if state is not None and item in (goal, overturn):
            at[item.action.value] = (state.score[0].goals, state.score[1].goals)
    assert at == {"shot": (3, 2), "var_overturned": (2, 2)}


def test_the_overturn_opens_an_epoch_at_the_score_before_the_goal(demo, overturn):
    ingest = Ingest()
    understanding = Understanding(ingest.record)
    for item in demo.items:
        ingest.accept(item)
        understanding.observe(item)
    goal = _goal(demo, overturn.overturns)
    by_start = {e.start_clock_ms: e for e in understanding.epochs}
    assert by_start[goal.clock_ms].trigger is EpochTrigger.GOAL
    reopened = by_start[overturn.clock_ms]
    assert reopened.trigger is EpochTrigger.VAR_OVERTURN
    assert sorted(reopened.score_state.values()) == [2, 2]


def test_every_claim_on_the_demo_passes_with_the_overturn_in_the_record(demo, overturn):
    ingest = Ingest()
    understanding = Understanding(ingest.record)
    spotter = Spotter(ingest.record, understanding.epoch_at)
    movement = Movement(ingest.frame_access, ingest.record)
    readings, positions, ruled = [], [], []
    for item in demo.items:
        ingest.accept(item)
        if isinstance(item, MatchSetup):
            continue
        batch = understanding.observe(item)
        readings += batch
        positions += movement.observe(item)
        for result in spotter.consider(batch, item):
            reader = ingest.record()
            log = FrozenLog(result.moment, reader, readings, understanding.epochs, positions)
            claims = explanation.explain(result.moment, log)
            record = verification.Record.of(reader, readings, positions)
            for claim in claims:
                v = verification.verify(claim, result.moment, claims, record)
                assert v.verdict is Verdict.PASS, (claim.claim_id, v.failure_reason)
            if result.moment.type is MomentType.GOAL_DISALLOWED:
                ruled.append((result.moment, claims, record))
    [(moment, claims, record)] = ruled
    assert moment.trigger_event_ids == (overturn.event_id, overturn.overturns)
    said = claims[0].operands[0]
    assert said.metric is Metric.RULED_OUT_OFFSIDE and said.subject.id == overturn.player
    score = claims[1].operands
    assert sorted(o.value for o in score) == [2.0, 2.0]  # the ruled-out goal is not in it

    # Saying the goal still stands, after the overturn, fails: the record has taken it back.
    wrong = claims[1].model_copy(
        update={"operands": (score[0].model_copy(update={"value": score[0].value + 1}), score[1])}
    )
    assert verification.verify(wrong, moment, claims, record).verdict is Verdict.FAIL


def _ruled_out_cards(cards: list[Card]) -> dict[str, Card]:
    return {c.rendition.lens_id: c for c in cards if c.moment_type is MomentType.GOAL_DISALLOWED}


def test_every_lens_shows_the_overturn_and_each_tells_it_differently(cards, demo, overturn):
    shown = _ruled_out_cards(cards)
    assert set(shown) == {"match_casual", "match_analyst", "team_engaged"}
    told = {lens: (c.rendition.headline, c.rendition.body) for lens, c in shown.items()}
    assert len(set(told.values())) == 3
    scorer = next(p.name for p in demo.setup.players if p.player_id == overturn.player)
    assert "offside" in (shown["match_casual"].rendition.body or "")
    assert "70 s review" in (shown["match_analyst"].rendition.body or "")
    # The team lens follows the side whose goal it was: their player, their loss, the level score.
    team = shown["team_engaged"].rendition
    assert scorer in (team.body or "") and "2–2" in (team.body or "")
    for card in shown.values():
        assert card.display_at_clock >= overturn.clock_ms  # never before the overturn (inv. 8)


def test_the_goal_card_that_went_out_first_is_not_changed(cards, overturn):
    goal_cards = [c for c in cards if c.rendition.moment_id == f"moment-{overturn.overturns}"]
    assert goal_cards and all(c.moment_type is MomentType.GOAL for c in goal_cards)
    assert all(c.display_at_clock < overturn.clock_ms for c in goal_cards)
