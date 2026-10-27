"""D4: a late joiner is told what their lens showed, once, and is sent none of it.

Most tests run seed 1's real cards through the router as a live match would: the cards up to
the join clock have arrived before the viewer does, the rest arrive after. On seed 1 the goals
are at 12:44 and 38:37 (Redfern United), then 57:59, 76:41 and 89:18 (Riverside Athletic), who
win 3-2, and the team lens follows Riverside Athletic.
"""

import re
import threading
from datetime import UTC, datetime

import pytest

from apps import pipeline
from matchlens import catchup, lenses
from matchlens.catchup import CatchUp
from matchlens.config import settings
from matchlens.control import Notice
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.models import Event, MomentType, Rendition, ViewerSession, standing_goals
from matchlens.rendering import Card
from matchlens.source import MatchSetup, simulate
from tests.delivery.test_http import LiveServer, _fields, _state
from tests.overlays import overlay_for

MINUTE = 60_000
JOIN = 68 * MINUTE
FULL_TIME = 200 * MINUTE  # past every card, stoppage time included
LENS_IDS = ("match_casual", "team_engaged", "match_analyst")


@pytest.fixture(scope="module")
def seed_one() -> list[Card]:
    cards: list[Card] = []
    pipeline.run(1, cards.append)
    return cards


def _join_live(
    cards: list[Card], lens_id: str, join_clock: int, offset: int = 0
) -> tuple[ReleaseQueues, ViewerSession]:
    """A session that joins the live match at `join_clock`, then watches to full time."""
    sessions, queues = SessionStore(), ReleaseQueues()
    router = CardRouter(sessions, queues)
    for card in cards:
        if card.display_at_clock <= join_clock:
            router.receive(card)
    lens = lenses.get(lens_id)
    session = sessions.create(lens_id, focus_team=lens.focus_team, stream_offset_ms=offset)
    router.join(session, join_clock)
    for card in cards:
        if card.display_at_clock > join_clock:
            router.receive(card)
    for clock in range(join_clock, FULL_TIME + offset, MINUTE):
        queues.release_due(session, clock)
    return queues, session


def _log(queues: ReleaseQueues, session: ViewerSession) -> list[Card | CatchUp]:
    """The session's cards and catch-up. No mute is in play here, so there is no notice."""
    log = queues.released(session.session_id)
    return [entry for entry in log if not isinstance(entry, Notice)]


def _scorers() -> set[str]:
    """The names of the players who scored on seed 1, from the record and not from any card."""
    items = list(simulate(1))
    setup = next(item for item in items if isinstance(item, MatchSetup))
    names = {player.player_id: player.name for player in setup.players}
    goals = standing_goals([e for e in items if isinstance(e, Event)])  # not one VAR ruled out
    return {names[e.player] for e in goals if e.player is not None}


def _summary(cards: list[Card], lens_id: str, to_clock: int = JOIN) -> CatchUp:
    summary = catchup.summarise(lenses.get(lens_id), cards, 0, to_clock)
    assert summary is not None
    return summary


# --- a summary, not the cards -------------------------------------------------------------------


@pytest.mark.parametrize("lens_id", LENS_IDS)
def test_a_68th_minute_joiner_gets_a_summary_of_0_to_68_and_none_of_those_cards(seed_one, lens_id):
    queues, session = _join_live(seed_one, lens_id, JOIN)
    first, *rest = _log(queues, session)
    assert isinstance(first, CatchUp)
    assert (first.from_clock, first.to_clock) == (0, JOIN)
    assert all(isinstance(entry, Card) and entry.display_at_clock > JOIN for entry in rest)


@pytest.mark.parametrize("lens_id", LENS_IDS)
def test_every_card_after_the_join_is_released_once_and_in_order(seed_one, lens_id):
    queues, session = _join_live(seed_one, lens_id, JOIN)
    released = [e for e in _log(queues, session) if isinstance(e, Card)]
    after = [c for c in seed_one if c.rendition.lens_id == lens_id and c.display_at_clock > JOIN]
    assert released == sorted(after, key=lambda c: c.display_at_clock)


def test_a_viewer_behind_is_summarised_to_where_their_video_is(seed_one):
    # 45 s behind at a live 68:00: the video is at 67:15, and the summary stops there.
    queues, session = _join_live(seed_one, "match_analyst", JOIN, offset=45_000)
    first, *rest = _log(queues, session)
    assert isinstance(first, CatchUp)
    assert first.to_clock == JOIN - 45_000
    assert all(isinstance(e, Card) and e.display_at_clock > JOIN - 45_000 for e in rest)


# --- per lens -------------------------------------------------------------------------------------


def test_three_lenses_joining_at_the_same_clock_get_three_summaries(seed_one):
    told = {
        lens_id: [(line.headline, line.body) for line in _summary(seed_one, lens_id).lines]
        for lens_id in LENS_IDS
    }
    assert len({tuple(lines) for lines in told.values()}) == 3


@pytest.mark.parametrize("lens_id", LENS_IDS)
def test_every_lens_is_told_the_goals_and_only_the_goals(seed_one, lens_id):
    goals = {
        c.rendition.moment_id
        for c in seed_one
        if c.moment_type is MomentType.GOAL and c.display_at_clock <= JOIN
    }
    assert len(goals) == 3  # 12:44, 38:37 and 57:59
    assert {line.moment_id for line in _summary(seed_one, lens_id).lines} == goals


@pytest.mark.parametrize("lens_id", LENS_IDS)
def test_a_goal_is_told_with_its_scorer_and_how_the_move_began(seed_one, lens_id):
    scorers = _scorers()
    lines = _summary(seed_one, lens_id).lines
    if lens_id == "team_engaged":
        # The team lens names only its own side's players: not the opponent's two scorers, and
        # Riverside's own scorer on the third goal.
        assert not any(name in line.body for line in lines[:2] for name in scorers)
        assert any(name in lines[2].body for name in scorers), lines[2].body
    else:
        for line in lines:
            assert any(name in line.body for name in scorers), line.body
    # The first goal came from winning the ball and a shot 12 seconds later, so every lens says
    # how. The second began with a throw-in, which is not an attack's start (D30): no claim.
    assert re.search(r"(quick|fast) attack", lines[0].body, re.IGNORECASE), lines[0].body
    assert not re.search(r"(quick|fast) attack", lines[1].body, re.IGNORECASE), lines[1].body


def test_the_casual_summary_says_how_without_a_number(seed_one):
    for line in _summary(seed_one, "match_casual").lines:
        assert not re.search(r"\d", f"{line.headline} {line.body}"), line.body


def test_the_team_summary_tells_each_goal_by_what_it_did_to_the_match(seed_one):
    opened, extended, trimmed = _summary(seed_one, "team_engaged").lines
    # Told for the side the lens follows: the first two goals are Riverside falling behind.
    assert re.search(r"fall behind|score first", opened.headline), opened.headline
    assert "Redfern United stretch their lead" in extended.headline or "fall" in extended.headline
    assert re.search(r"pull one back|cut the deficit", trimmed.headline), trimmed.headline
    assert "Riverside Athletic" in trimmed.headline
    for line in (opened, extended, trimmed):
        assert not re.search(r"\b(we|us|our)\b", line.body, re.IGNORECASE)  # D31


def test_the_team_summary_says_where_a_goal_leaves_the_side_before_who_scored(seed_one):
    *_, trimmed = _summary(seed_one, "team_engaged").lines
    assert trimmed.body.startswith("Riverside Athletic trail 1–2")


def test_with_no_goals_yet_a_joiner_is_told_the_most_important_moments(seed_one):
    # The same match with its goals taken out, which is a match nobody has scored in yet.
    goalless = [c for c in seed_one if c.moment_type is not MomentType.GOAL]
    early = [c for c in goalless if c.display_at_clock <= 40 * MINUTE]
    analyst = [c for c in early if c.rendition.lens_id == "match_analyst"]
    assert len(analyst) > settings.catchup_key_moments
    summary = catchup.summarise(lenses.get("match_analyst"), goalless, 0, 40 * MINUTE)
    assert summary is not None
    lines = summary.lines
    top = sorted(analyst, key=lambda c: (-c.importance, c.display_at_clock))
    chosen = {c.rendition.moment_id for c in top[: settings.catchup_key_moments]}
    assert {line.moment_id for line in lines} == chosen
    assert [line.clock_ms for line in lines] == sorted(line.clock_ms for line in lines)


# --- nothing invented (invariant 5) ---------------------------------------------------------------


@pytest.mark.parametrize("lens_id", LENS_IDS)
@pytest.mark.parametrize("join", [15 * MINUTE, JOIN, FULL_TIME])
def test_every_line_is_a_card_the_lens_showed_in_the_window(seed_one, lens_id, join):
    shown = {
        c.rendition.rendition_id: c
        for c in seed_one
        if c.rendition.lens_id == lens_id and c.display_at_clock <= join
    }
    summary = catchup.summarise(lenses.get(lens_id), seed_one, 0, join)
    for line in summary.lines if summary else ():
        card = shown[line.rendition_id]
        assert line.moment_id == card.rendition.moment_id
        assert line.claim_ids == card.rendition.surviving_claim_ids
        assert line.clock_ms == card.display_at_clock
        assert (line.headline, line.body) == (card.rendition.headline, card.body_in_full)
        # The card's own words come first; anything after them is a claim it did not speak.
        assert card.body_in_full.startswith(card.rendition.body or "")


def test_a_full_detail_card_is_already_told_in_full(seed_one):
    # A card speaks the first few claims Selection kept; the catch-up speaks them all. So the
    # catch-up body is the card's body where the lens kept no more than a card speaks, and
    # otherwise only adds claims Selection kept, never new sentences.
    analyst = [c for c in seed_one if c.rendition.lens_id == "match_analyst"]
    assert analyst
    for card in analyst:
        if len(card.rendition.surviving_claim_ids) <= settings.claims_spoken_full:
            assert card.body_in_full == card.rendition.body
        else:
            assert len(card.body_in_full) >= len(card.rendition.body or "")


# --- once, and never when there is nothing to say -------------------------------------------------


def test_the_summary_is_in_the_log_once_however_many_releases_follow(seed_one):
    queues, session = _join_live(seed_one, "match_casual", JOIN)
    log = _log(queues, session)
    assert sum(isinstance(e, CatchUp) for e in log) == 1
    assert not any(isinstance(e, CatchUp) for e in queues.released(session.session_id, 1))


@pytest.mark.parametrize("lens_id", LENS_IDS)
@pytest.mark.parametrize("offset", [0, 45_000])
def test_a_viewer_joining_at_kickoff_gets_no_summary(seed_one, lens_id, offset):
    queues, session = _join_live(seed_one, lens_id, 0, offset=offset)
    assert not any(isinstance(e, CatchUp) for e in _log(queues, session))


def test_a_joiner_whose_lens_has_said_nothing_yet_gets_no_summary(seed_one):
    assert catchup.summarise(lenses.get("match_casual"), seed_one, 0, 12 * MINUTE) is None
    queues, session = _join_live(seed_one, "match_casual", 12 * MINUTE)
    assert not any(isinstance(e, CatchUp) for e in _log(queues, session))


def test_a_summary_held_for_a_lens_the_session_has_left_is_not_sent(seed_one):
    sessions, queues = SessionStore(), ReleaseQueues()
    router = CardRouter(sessions, queues)
    for card in seed_one:
        if card.display_at_clock <= JOIN:
            router.receive(card)
    session = sessions.create("match_casual")
    router.join(session, JOIN)
    moved = sessions.switch_lens(session.session_id, "match_analyst")
    queues.release_due(moved, JOIN)
    assert not any(isinstance(e, CatchUp) for e in _log(queues, moved))


# --- over the stream ------------------------------------------------------------------------------


def _held(lens_id: str) -> CatchUp:
    rendition = Rendition(
        rendition_id=f"g:{lens_id}", moment_id="g", lens_id=lens_id, language="en",
        headline="Goal!", body="b", surviving_claim_ids=("g:c1",), suppressed=False,
        suppression_reason=None, rendered_at=datetime.now(UTC), model="templates",
        model_version="t",
    )  # fmt: skip
    card = Card(
        rendition=rendition, display_at_clock=MINUTE, moment_type=MomentType.GOAL,
        importance=1.0, body_in_full="b c1", overlay=overlay_for(rendition, MINUTE),
    )  # fmt: skip
    summary = catchup.summarise(lenses.get(lens_id), [card], 0, 2 * MINUTE)
    assert summary is not None
    return summary


@pytest.fixture
def live(queues: ReleaseQueues):
    with LiveServer(MatchStateHub(), queues) as server:
        yield server


@pytest.fixture
def queues() -> ReleaseQueues:
    return ReleaseQueues()


def test_the_stream_sends_the_summary_first_and_a_reconnect_does_not_repeat_it(live, queues):
    session_id = live.session()
    session = live.sessions.get(session_id)
    queues.hold_catch_up(_held(session.lens_id), session)
    live.publish(_state(seq=3, clock_ms=2 * MINUTE))
    state, summary = live.events(session_id, 2)
    assert _fields(summary)["event"] == "catch_up"
    assert _fields(summary)["id"] == "3:1"

    threading.Timer(0.3, live.publish, (_state(seq=5, clock_ms=3 * MINUTE),)).start()
    for last_event_id in ("3:1", None):  # a reconnect, then a fresh page on the same session
        blocks = live.events(session_id, 1, last_event_id=last_event_id)
        assert all(_fields(b).get("event") != "catch_up" for b in blocks)
