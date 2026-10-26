"""P2: a mute stops later cards at the router, and the viewer is told through their own release
queue (Q44: 1A, 2B, 3A).

The router drops what arrives after a mute and touches nothing already queued. A notice is held
in each session's queue at the mute's clock, so it follows any cards the viewer is still owed and
waits for their video; whether they "had cards" is judged when it is released, from
`last_seen_clock`, which is None until their first card.
"""

import json

import pytest

from matchlens.control import Mutes, Notice, NoticeKind
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.models import ViewerSession
from tests.delivery.test_http import LiveServer, _fields, _state
from tests.delivery.test_release import _card

CASUAL = "match_casual"
ANALYST = "match_analyst"
SECOND = 1_000
MINUTE = 60_000


class Rig:
    """Sessions, queues and a router that share one `Mutes`, as the delivery app wires them."""

    def __init__(self) -> None:
        self.sessions = SessionStore()
        self.queues = ReleaseQueues()
        self.mutes = Mutes()
        self.router = CardRouter(self.sessions, self.queues, self.mutes)

    def mute(self, lens_id: str, at_clock: int) -> None:
        self.router.notify(Notice.of(self.mutes.mute(lens_id, at_clock, "ops", "wrong player")))

    def unmute(self, lens_id: str, at_clock: int) -> None:
        self.router.notify(Notice.of(self.mutes.unmute(lens_id, at_clock, "ops", "fixed")))

    def see_a_card(self, session: ViewerSession, clock: int) -> ViewerSession:
        """Send the session one card, and release it when their video reaches it."""
        self.router.receive(_card(clock, session.lens_id))
        self.release(session, clock + session.stream_offset_ms)
        return self.sessions.get(session.session_id)

    def release(self, session: ViewerSession, match_clock_now: int) -> None:
        """Release what is due to the session and note the last card seen, as the stream does."""
        released = self.queues.release_due(self.sessions.get(session.session_id), match_clock_now)
        if released:
            self.sessions.mark_seen(session.session_id, released[-1].display_at_clock)

    def notices(self, session: ViewerSession) -> list[Notice]:
        log = self.queues.released(session.session_id)
        return [entry for entry in log if isinstance(entry, Notice)]


@pytest.fixture
def rig() -> Rig:
    return Rig()


# --- what a mute stops --------------------------------------------------------------------------


def test_muting_a_lens_stops_its_later_cards_and_nothing_else(rig: Rig):
    casual, analyst = rig.sessions.create(CASUAL), rig.sessions.create(ANALYST)
    rig.mutes.mute(CASUAL, 10 * MINUTE, "ops", "wrong player")
    rig.router.receive(_card(11 * MINUTE, CASUAL))
    rig.router.receive(_card(11 * MINUTE, ANALYST))
    assert rig.queues.depth(casual.session_id) == 0
    assert [card.display_at_clock for card in rig.queues.release_due(analyst, 11 * MINUTE)] == [
        11 * MINUTE
    ]


def test_cards_already_queued_still_release_at_their_own_times(rig: Rig):
    behind = rig.sessions.create(CASUAL, stream_offset_ms=45 * SECOND)
    rig.router.receive(_card(10 * MINUTE, CASUAL))  # queued before the click
    rig.mutes.mute(CASUAL, 10 * MINUTE + 20 * SECOND, "ops", "wrong player")
    rig.router.receive(_card(10 * MINUTE + 30 * SECOND, CASUAL))  # after it: stopped

    assert rig.queues.depth(behind.session_id) == 1  # nothing swept, and the later one not queued
    assert rig.queues.release_due(behind, 10 * MINUTE + 20 * SECOND) == []  # not due: delay stays
    released = rig.queues.release_due(behind, 10 * MINUTE + 50 * SECOND)
    assert [card.display_at_clock for card in released] == [10 * MINUTE]


def test_an_unmute_resumes_cards_from_that_clock_and_does_not_back_fill(rig: Rig):
    session = rig.sessions.create(CASUAL)
    rig.mutes.mute(CASUAL, 10 * MINUTE, "ops", "wrong player")
    rig.router.receive(_card(12 * MINUTE, CASUAL))
    rig.mutes.unmute(CASUAL, 20 * MINUTE, "ops", "fixed")
    rig.router.receive(_card(15 * MINUTE, CASUAL))  # from inside the mute, arriving late
    rig.router.receive(_card(21 * MINUTE, CASUAL))
    released = rig.queues.release_due(session, 30 * MINUTE)
    assert [card.display_at_clock for card in released] == [21 * MINUTE]


def test_a_card_arriving_while_muted_is_stopped_even_for_an_earlier_moment(rig: Rig):
    session = rig.sessions.create(CASUAL)
    rig.mutes.mute(CASUAL, 10 * MINUTE, "ops", "wrong player")
    rig.router.receive(_card(8 * MINUTE, CASUAL))
    assert rig.queues.depth(session.session_id) == 0


def test_a_card_the_router_stops_is_logged_since_no_rendition_records_it(rig: Rig, caplog):
    rig.sessions.create(CASUAL)
    rig.mutes.mute(CASUAL, 10 * MINUTE, "ops", "wrong player")
    with caplog.at_level("INFO"):
        rig.router.receive(_card(11 * MINUTE, CASUAL, moment_id="m-goal"))
    assert any("m-goal" in record.getMessage() for record in caplog.records)


# --- who is told, and when ----------------------------------------------------------------------


def test_a_viewer_who_had_cards_is_told_when_their_video_reaches_the_mute(rig: Rig):
    session = rig.see_a_card(rig.sessions.create(CASUAL), 5 * MINUTE)
    rig.mute(CASUAL, 10 * MINUTE)
    rig.release(session, 10 * MINUTE)
    assert rig.notices(session) == [
        Notice(lens_id=CASUAL, kind=NoticeKind.PAUSED, clock_ms=10 * MINUTE)
    ]


def test_a_viewer_who_had_no_cards_is_not_told(rig: Rig):
    session = rig.sessions.create(CASUAL)
    assert session.last_seen_clock is None
    rig.mute(CASUAL, 10 * MINUTE)
    rig.release(session, 10 * MINUTE)
    assert rig.notices(session) == []


def test_the_notice_waits_behind_the_cards_a_viewer_behind_is_still_owed(rig: Rig):
    behind = rig.sessions.create(CASUAL, stream_offset_ms=45 * SECOND)
    behind = rig.see_a_card(behind, 5 * MINUTE)
    rig.router.receive(_card(10 * MINUTE, CASUAL))  # owed, due at their 10:00
    rig.mute(CASUAL, 10 * MINUTE + 20 * SECOND)

    rig.release(behind, 10 * MINUTE + 50 * SECOND)  # their video is at 10:05
    assert [type(entry).__name__ for entry in rig.queues.released(behind.session_id)][-1] == "Card"
    assert rig.notices(behind) == []  # not before they have seen what the lens said

    rig.release(behind, 11 * MINUTE + 10 * SECOND)  # their video reaches 10:25
    assert [notice.kind for notice in rig.notices(behind)] == [NoticeKind.PAUSED]


def test_a_viewer_whose_first_card_is_released_in_the_same_batch_as_the_notice_is_told(rig: Rig):
    session = rig.sessions.create(CASUAL, stream_offset_ms=45 * SECOND)
    rig.router.receive(_card(10 * MINUTE, CASUAL))
    rig.mute(CASUAL, 10 * MINUTE + 20 * SECOND)
    assert session.last_seen_clock is None

    rig.release(session, 12 * MINUTE)  # both are due at once: the card, then the notice
    kinds = [type(entry).__name__ for entry in rig.queues.released(session.session_id)]
    assert kinds == ["Card", "Notice"]


def test_an_unmute_is_told_only_to_a_viewer_who_was_told_of_the_pause(rig: Rig):
    told = rig.see_a_card(rig.sessions.create(CASUAL), 5 * MINUTE)
    never_saw_a_card = rig.sessions.create(CASUAL)
    rig.mute(CASUAL, 10 * MINUTE)
    rig.unmute(CASUAL, 20 * MINUTE)
    rig.release(told, 25 * MINUTE)
    rig.release(never_saw_a_card, 25 * MINUTE)

    assert [notice.kind for notice in rig.notices(told)] == [NoticeKind.PAUSED, NoticeKind.RESUMED]
    assert [notice.clock_ms for notice in rig.notices(told)] == [10 * MINUTE, 20 * MINUTE]
    assert rig.notices(never_saw_a_card) == []


def test_a_notice_for_a_lens_the_viewer_has_left_is_not_sent(rig: Rig):
    session = rig.see_a_card(rig.sessions.create(CASUAL), 5 * MINUTE)
    rig.mute(CASUAL, 10 * MINUTE)
    rig.sessions.switch_lens(session.session_id, ANALYST)
    rig.release(session, 11 * MINUTE)
    assert rig.notices(session) == []


def test_only_sessions_on_the_muted_lens_are_told(rig: Rig):
    casual = rig.see_a_card(rig.sessions.create(CASUAL), 5 * MINUTE)
    analyst = rig.see_a_card(rig.sessions.create(ANALYST), 5 * MINUTE)
    rig.mute(CASUAL, 10 * MINUTE)
    rig.release(casual, 11 * MINUTE)
    rig.release(analyst, 11 * MINUTE)
    assert len(rig.notices(casual)) == 1
    assert rig.notices(analyst) == []


def test_a_viewer_who_joins_behind_the_mute_is_given_the_notice_in_their_own_time(rig: Rig):
    rig.router.receive(_card(9 * MINUTE + 50 * SECOND, CASUAL))  # before the mute
    rig.mute(CASUAL, 10 * MINUTE)
    late = rig.sessions.create(CASUAL, stream_offset_ms=45 * SECOND)
    rig.router.join(late, 10 * MINUTE + 30 * SECOND)  # their video is at 9:45, before the mute

    rig.release(late, 10 * MINUTE + 40 * SECOND)  # video at 9:55: the card, not yet the notice
    assert rig.queues.count_released(late.session_id) == 1
    assert rig.notices(late) == []
    rig.release(late, 10 * MINUTE + 50 * SECOND)  # video at 10:05
    assert [notice.kind for notice in rig.notices(late)] == [NoticeKind.PAUSED]


def test_a_notice_is_counted_in_the_log_so_a_reconnect_resumes_after_it(rig: Rig):
    session = rig.see_a_card(rig.sessions.create(CASUAL), 5 * MINUTE)
    rig.mute(CASUAL, 10 * MINUTE)
    rig.release(session, 10 * MINUTE)
    assert rig.queues.count_released(session.session_id) == 2  # the card, then the notice


# --- on the stream ------------------------------------------------------------------------------


@pytest.fixture
def queues() -> ReleaseQueues:
    return ReleaseQueues()


@pytest.fixture
def live(queues: ReleaseQueues):
    with LiveServer(MatchStateHub(), queues) as server:
        yield server


def test_a_notice_is_its_own_stream_event_counted_like_a_card(live: LiveServer, queues):
    session_id = live.session()
    session = live.sessions.get(session_id)
    queues.enqueue(_card(SECOND, session.lens_id), session)
    queues.enqueue_notice(
        Notice(lens_id=session.lens_id, kind=NoticeKind.PAUSED, clock_ms=2 * SECOND), session
    )
    live.publish(_state(seq=3, clock_ms=3 * SECOND))

    blocks = live.events(session_id, 3)
    assert [_fields(block)["event"] for block in blocks] == ["match_state", "card", "notice"]
    notice = _fields(blocks[2])
    assert notice["id"] == "3:2"
    assert json.loads(notice["data"]) == {
        "lens_id": session.lens_id,
        "kind": "paused",
        "clock_ms": 2 * SECOND,
    }


def test_a_reconnect_after_the_card_is_sent_the_notice_and_not_the_card_again(live, queues):
    session_id = live.session()
    session = live.sessions.get(session_id)
    queues.enqueue(_card(SECOND, session.lens_id), session)
    queues.enqueue_notice(
        Notice(lens_id=session.lens_id, kind=NoticeKind.PAUSED, clock_ms=2 * SECOND), session
    )
    live.publish(_state(seq=3, clock_ms=3 * SECOND))
    live.events(session_id, 3)

    [resumed] = live.events(session_id, 1, last_event_id="3:1")
    assert _fields(resumed)["event"] == "notice"
