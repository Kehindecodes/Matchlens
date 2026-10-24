"""D1: the per-session release queue. Delay only, never anticipate (invariant 8, V8).

The rule is read on the queue head, on the match clock, per session. Most tests drive
`ReleaseQueues` directly with a clock in match milliseconds; the stream tests use the live
server from `test_http`; the last ones run seed 1's real cards through the router.
"""

import asyncio
import json
import threading
from datetime import UTC, datetime

import pytest

from apps import pipeline
from apps.delivery import run_local_feed
from matchlens.config import settings
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.models import Frame, Phase, Rendition, ViewerSession
from matchlens.rendering import Card
from matchlens.source import MatchSetup, simulate
from matchlens.source.replay import Replay
from tests.delivery.test_http import LiveServer, _fields, _state

SECOND = 1_000
OFFSET = 45 * SECOND


def _card(clock: int, lens_id: str = settings.default_lens_id, moment_id: str = "") -> Card:
    moment_id = moment_id or f"m{clock}"
    rendition = Rendition(
        rendition_id=f"{moment_id}:{lens_id}", moment_id=moment_id, lens_id=lens_id,
        language="en", headline="h", body="b", surviving_claim_ids=(), suppressed=False,
        suppression_reason=None, rendered_at=datetime.now(UTC),
    )  # fmt: skip
    return Card(rendition=rendition, display_at_clock=clock)


def _clocks(cards: list[Card]) -> list[int]:
    return [c.display_at_clock for c in cards]


def _behind(offset: int = OFFSET) -> tuple[SessionStore, ReleaseQueues, ViewerSession]:
    sessions = SessionStore()
    return sessions, ReleaseQueues(), sessions.create(stream_offset_ms=offset)


# --- never early (V8) ----------------------------------------------------------------------------


def test_a_card_waits_until_the_viewers_video_reaches_it():
    _, queues, session = _behind()
    queues.enqueue(_card(60 * SECOND), session)
    assert queues.release_due(session, 60 * SECOND) == []  # the action, not the viewer
    assert queues.release_due(session, 60 * SECOND + OFFSET - 1) == []
    assert _clocks(queues.release_due(session, 60 * SECOND + OFFSET)) == [60 * SECOND]


def test_no_card_is_ever_released_before_its_clock_less_the_offset():
    _, queues, session = _behind()
    for clock in range(0, 600 * SECOND, 7 * SECOND):
        queues.enqueue(_card(clock), session)
    for now in range(0, 700 * SECOND, 500):
        for card in queues.release_due(session, now):
            assert card.display_at_clock <= now - OFFSET


def test_a_kickoff_card_waits_for_a_viewer_still_before_kickoff():
    _, queues, session = _behind()
    queues.enqueue(_card(0), session)
    assert queues.release_due(session, OFFSET - 1) == []
    assert _clocks(queues.release_due(session, OFFSET)) == [0]


def test_a_viewer_with_no_offset_sees_a_card_at_its_clock():
    _, queues, session = _behind(offset=0)
    queues.enqueue(_card(5 * SECOND), session)
    assert _clocks(queues.release_due(session, 5 * SECOND)) == [5 * SECOND]


# --- the head of the queue -----------------------------------------------------------------------


def test_the_release_order_is_the_clock_order_not_the_arrival_order():
    _, queues, session = _behind(offset=0)
    for clock in (30 * SECOND, 10 * SECOND, 20 * SECOND):
        queues.enqueue(_card(clock), session)
    released = queues.release_due(session, 30 * SECOND)
    assert _clocks(released) == [10 * SECOND, 20 * SECOND, 30 * SECOND]


def test_a_card_not_yet_due_holds_the_cards_behind_it():
    _, queues, session = _behind(offset=0)
    for clock in (10 * SECOND, 40 * SECOND, 50 * SECOND):
        queues.enqueue(_card(clock), session)
    assert _clocks(queues.release_due(session, 45 * SECOND)) == [10 * SECOND, 40 * SECOND]
    assert queues.depth(session.session_id) == 1
    # A card arriving now for earlier in the match goes ahead of the one still held.
    queues.enqueue(_card(42 * SECOND), session)
    assert _clocks(queues.release_due(session, 45 * SECOND)) == [42 * SECOND]
    assert _clocks(queues.release_due(session, 50 * SECOND)) == [50 * SECOND]


def test_cards_on_the_same_clock_keep_the_order_they_arrived_in():
    _, queues, session = _behind(offset=0)
    first, second = _card(SECOND, moment_id="first"), _card(SECOND, moment_id="second")
    queues.enqueue(first, session)
    queues.enqueue(second, session)
    assert queues.release_due(session, SECOND) == [first, second]


# --- per session ---------------------------------------------------------------------------------


def test_two_sessions_on_one_lens_with_different_offsets_hold_different_depths():
    sessions, queues = SessionStore(), ReleaseQueues()
    near = sessions.create(stream_offset_ms=5 * SECOND)
    far = sessions.create(stream_offset_ms=OFFSET)
    router = CardRouter(sessions, queues)
    for clock in range(0, 60 * SECOND, 10 * SECOND):
        router.receive(_card(clock))
    now = 54 * SECOND
    queues.release_due(near, now)
    queues.release_due(far, now)
    assert queues.depth(near.session_id) == 1  # 50 s is not yet on the 5 s viewer's screen
    assert queues.depth(far.session_id) == 5  # only kickoff has reached the 45 s viewer


def test_the_offset_is_set_when_the_session_is_made_and_cannot_be_negative():
    assert SessionStore().create(stream_offset_ms=OFFSET).stream_offset_ms == OFFSET
    with pytest.raises(ValueError):
        SessionStore().create(stream_offset_ms=-1)


# --- the final whistle ---------------------------------------------------------------------------


def test_a_card_held_at_full_time_is_released_when_the_clock_runs_on():
    hub = MatchStateHub()
    _, queues, session = _behind()
    full_time = 95 * 60 * SECOND
    queues.enqueue(_card(full_time - SECOND), session)

    async def run() -> list[Card]:
        await hub.publish(_state(seq=1, clock_ms=full_time))  # the last state there will be
        held = queues.release_due(session, hub.clock_ms)
        assert held == []
        await hub.advance(full_time + OFFSET)
        return queues.release_due(session, hub.clock_ms)

    assert _clocks(asyncio.run(run())) == [full_time - SECOND]
    assert queues.depth(session.session_id) == 0


def test_the_hub_clock_never_goes_back():
    hub = MatchStateHub()

    async def run() -> int:
        await hub.advance(10 * SECOND)
        await hub.advance(5 * SECOND)
        await hub.publish(_state(seq=1, clock_ms=SECOND))
        return hub.clock_ms

    assert asyncio.run(run()) == 10 * SECOND


def test_the_local_feed_keeps_the_clock_running_after_the_last_item():
    setup = next(iter(simulate(1)))
    assert isinstance(setup, MatchSetup)
    frames = [
        Frame(
            seq=i, clock_ms=i * 500, period=1, phase=Phase.IN_PLAY, ball_x=0.0, ball_y=0.0,
            ball_z=0.0, ball_speed=0.0, carrier=None, players=(),
        )
        for i in range(4)
    ]  # fmt: skip
    hub = MatchStateHub()
    replay = Replay([setup, *frames], speed=100.0)

    async def run() -> int:
        feed = asyncio.create_task(
            run_local_feed(hub, replay, pipeline.Pipeline(), lambda card: None)
        )
        await asyncio.sleep(0.6)  # 60 match seconds at 100x, the stream lasts 1.5
        feed.cancel()
        return hub.clock_ms

    assert asyncio.run(run()) > 30 * SECOND
    assert replay.finished


# --- the stream: last_seen_clock, rejoin and resume ----------------------------------------------


@pytest.fixture
def queues() -> ReleaseQueues:
    return ReleaseQueues()


@pytest.fixture
def live(queues: ReleaseQueues):
    with LiveServer(MatchStateHub(), queues) as server:
        yield server


def _cards(blocks: list[list[str]]) -> list[tuple[str, int]]:
    out = []
    for block in blocks:
        fields = _fields(block)
        if fields.get("event") == "card":
            out.append((fields["id"], json.loads(fields["data"])["display_at_clock"]))
    return out


def test_last_seen_clock_advances_as_cards_release(live, queues):
    session_id = live.session()
    session = live.sessions.get(session_id)
    assert session.last_seen_clock is None
    for clock in (SECOND, 2 * SECOND, 9 * SECOND):
        queues.enqueue(_card(clock), session)
    live.publish(_state(seq=3, clock_ms=3 * SECOND))
    live.events(session_id, 3)  # the state and the two cards due
    assert live.sessions.get(session_id).last_seen_clock == 2 * SECOND


def test_a_rejoin_replays_nothing_already_seen(live, queues):
    session_id = live.session()
    session = live.sessions.get(session_id)
    queues.enqueue(_card(SECOND), session)
    live.publish(_state(seq=3, clock_ms=3 * SECOND))
    assert _cards(live.events(session_id, 2)) == [("3:1", SECOND)]

    # A fresh page on the same session: no Last-Event-ID. The next thing it gets is new.
    queues.enqueue(_card(4 * SECOND), session)
    threading.Timer(0.3, live.publish, (_state(seq=5, clock_ms=5 * SECOND),)).start()
    blocks = live.events(session_id, 3)
    assert _cards(blocks) == [("5:2", 4 * SECOND)]


def test_a_reconnect_with_last_event_id_resumes_after_that_card(live, queues):
    session_id = live.session()
    session = live.sessions.get(session_id)
    for clock in (SECOND, 2 * SECOND):
        queues.enqueue(_card(clock), session)
    live.publish(_state(seq=3, clock_ms=3 * SECOND))
    state, first, second = live.events(session_id, 3)
    assert _fields(first)["id"] == "3:1"

    # The connection dropped after the first card: the second is sent at once, the first is not,
    # and the state the browser already has is not sent again.
    resumed = live.events(session_id, 1, last_event_id="3:1")
    assert _cards(resumed) == [("3:2", 2 * SECOND)]


def test_a_new_session_with_an_offset_is_refused_if_negative(live):
    assert live.client.post("/session", json={"stream_offset_ms": -1}).status_code == 422
    made = live.client.post("/session", json={"stream_offset_ms": OFFSET}).json()
    assert made["stream_offset_ms"] == OFFSET


# --- seed 1, end to end --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def demo_cards() -> list[Card]:
    cards: list[Card] = []
    pipeline.run(settings.match_seed, cards.append)
    return cards


def _replay(cards: list[Card], offsets: tuple[int, ...]) -> tuple[list[tuple], dict]:
    """Drive the clock a second at a time to a minute past the last card, as the feed would."""
    sessions, queues = SessionStore(), ReleaseQueues()
    lens_id = cards[0].rendition.lens_id
    viewers = [sessions.create(lens_id=lens_id, stream_offset_ms=o) for o in offsets]
    router = CardRouter(sessions, queues)
    arriving = iter(c for c in cards if c.rendition.lens_id == lens_id)
    upcoming = next(arriving, None)
    end = cards[-1].display_at_clock + max(offsets) + 60 * SECOND
    log, depth_at_full_time = [], {}
    for now in range(0, end, SECOND):
        while upcoming is not None and upcoming.display_at_clock <= now:
            router.receive(upcoming)
            upcoming = next(arriving, None)
        for viewer in viewers:
            for card in queues.release_due(viewer, now):
                assert card.display_at_clock <= now - viewer.stream_offset_ms  # V8
                log.append((now, viewer.stream_offset_ms, card.rendition.rendition_id))
        if upcoming is None and not depth_at_full_time:
            depth_at_full_time = {v.stream_offset_ms: queues.depth(v.session_id) for v in viewers}
    held = {v.stream_offset_ms: queues.depth(v.session_id) for v in viewers}
    return log, {"at_full_time": depth_at_full_time, "at_end": held}


def test_seed_one_releases_every_card_never_early_and_the_same_way_twice(demo_cards):
    offsets = (5 * SECOND, OFFSET)
    log, depths = _replay(demo_cards, offsets)
    again, _ = _replay(demo_cards, offsets)
    assert log == again
    shown = [c for c in demo_cards if c.rendition.lens_id == demo_cards[0].rendition.lens_id]
    for offset in offsets:
        assert len([e for e in log if e[1] == offset]) == len(shown)  # nothing dropped
    assert depths["at_end"] == {5 * SECOND: 0, OFFSET: 0}


def test_seed_one_leaves_cards_held_at_full_time_for_a_viewer_behind(demo_cards):
    _, depths = _replay(demo_cards, (0, OFFSET))
    assert depths["at_full_time"][0] == 0
    assert depths["at_full_time"][OFFSET] > 0
