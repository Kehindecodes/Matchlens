"""P2: the producer's controls (Q44: 4A) and what a mute leaves on the producer view.

Mute and unmute exist only where the producer view does, so a viewer has nothing to call. Each
writes a `ProducerAction`, stops later cards on one lens, tells the viewers who had cards, and
leaves the match clock alone.
"""

import asyncio
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from matchlens import lenses
from matchlens.control import Mutes, Notice, NoticeKind
from matchlens.delivery.http import WEB_DIR, create_app
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.producer import LensState, ProducerFeed
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.models import ProducerActionType, Rendition
from tests.delivery.test_http import LiveServer, _fields
from tests.delivery.test_release import _card

CASUAL = "match_casual"
ANALYST = "match_analyst"
SECOND = 1_000
MINUTE = 60_000
CLOCK_MS = 51 * MINUTE + 9 * SECOND


@dataclass
class Rig:
    hub: MatchStateHub
    sessions: SessionStore
    queues: ReleaseQueues
    mutes: Mutes
    router: CardRouter
    feed: ProducerFeed
    client: TestClient

    def mute(self, lens_id: str = CASUAL, reason: str = "named the wrong player", **extra):
        body = {"lens_id": lens_id, "reason": reason, **extra}
        return self.client.post("/producer/mute", json=body)

    def unmute(self, lens_id: str = CASUAL, reason: str = "fixed", **extra):
        body = {"lens_id": lens_id, "reason": reason, **extra}
        return self.client.post("/producer/unmute", json=body)

    def clock(self) -> int:
        return self.client.get("/playback").json()["clock_ms"]


@pytest.fixture
def rig() -> Iterator[Rig]:
    hub = MatchStateHub()
    asyncio.run(hub.advance(CLOCK_MS))
    sessions, queues, mutes = SessionStore(), ReleaseQueues(), Mutes()
    router = CardRouter(sessions, queues, mutes)
    feed = ProducerFeed(lenses.all_lenses(), mutes)
    app = create_app(hub, sessions, queues, router, producer=feed, mutes=mutes)
    with TestClient(app) as client:
        yield Rig(hub, sessions, queues, mutes, router, feed, client)


# --- who can call it ----------------------------------------------------------------------------


def test_without_the_producer_view_there_is_no_mute_to_call():
    with TestClient(create_app(MatchStateHub(), SessionStore())) as client:
        body = {"lens_id": CASUAL, "reason": "named the wrong player"}
        assert client.post("/producer/mute", json=body).status_code == 404
        assert client.post("/producer/unmute", json=body).status_code == 404
        assert client.get("/producer/actions").status_code == 404


def test_a_viewer_page_has_nothing_that_mutes():
    for path in WEB_DIR.iterdir():
        if path.suffix in {".html", ".js"} and not path.name.startswith("producer"):
            assert "/mute" not in path.read_text(), path.name


# --- what a mute does ---------------------------------------------------------------------------


def test_muting_a_lens_logs_a_producer_action_at_the_live_clock(rig: Rig):
    response = rig.mute(actor="dana")
    assert response.status_code == 201
    action = response.json()
    assert action["action"] == ProducerActionType.SUPPRESS.value
    assert action["target_id"] == {"kind": "lens", "id": CASUAL}
    assert action["actor"] == "dana"
    assert action["reason"] == "named the wrong player"
    assert action["clock_ms"] == CLOCK_MS


def test_the_actor_defaults_to_producer_since_there_are_no_accounts(rig: Rig):
    assert rig.mute().json()["actor"] == "producer"


def test_every_mute_and_unmute_is_listed_with_its_actor_and_reason_in_order(rig: Rig):
    rig.mute(actor="dana")
    rig.unmute(actor="dana", reason="fixed the name")
    actions = rig.client.get("/producer/actions").json()
    assert [action["action"] for action in actions] == ["suppress", "release"]
    assert [action["reason"] for action in actions] == ["named the wrong player", "fixed the name"]
    assert {action["actor"] for action in actions} == {"dana"}


def test_a_reason_is_required(rig: Rig):
    assert rig.client.post("/producer/mute", json={"lens_id": CASUAL}).status_code == 422
    assert rig.mute(reason="").status_code == 422
    assert rig.mute(reason="   ").status_code == 422
    assert rig.mutes.actions() == []


def test_an_unknown_lens_cannot_be_muted(rig: Rig):
    assert rig.mute(lens_id="not_a_lens").status_code == 404
    assert rig.mutes.actions() == []


def test_a_muted_lens_cannot_be_muted_again_and_an_unmuted_one_cannot_be_unmuted(rig: Rig):
    assert rig.unmute().status_code == 409
    assert rig.mute().status_code == 201
    assert rig.mute().status_code == 409
    assert len(rig.mutes.actions()) == 1


def test_muting_a_lens_stops_its_later_cards_and_no_other_lens(rig: Rig):
    casual, analyst = rig.sessions.create(CASUAL), rig.sessions.create(ANALYST)
    rig.mute()
    rig.router.receive(_card(CLOCK_MS + SECOND, CASUAL))
    rig.router.receive(_card(CLOCK_MS + SECOND, ANALYST))
    assert rig.queues.release_due(casual, CLOCK_MS + MINUTE) == []  # a notice waits, no card
    released = rig.queues.release_due(analyst, CLOCK_MS + MINUTE)
    assert [card.display_at_clock for card in released] == [CLOCK_MS + SECOND]


def test_unmuting_resumes_cards_from_that_clock_and_does_not_back_fill(rig: Rig):
    session = rig.sessions.create(CASUAL)
    rig.mute()
    rig.router.receive(_card(CLOCK_MS + SECOND, CASUAL))
    asyncio.run(rig.hub.advance(CLOCK_MS + 10 * SECOND))
    rig.unmute()
    rig.router.receive(_card(CLOCK_MS + 5 * SECOND, CASUAL))  # from inside the mute, late
    rig.router.receive(_card(CLOCK_MS + 11 * SECOND, CASUAL))
    released = rig.queues.release_due(session, CLOCK_MS + MINUTE)
    assert [card.display_at_clock for card in released] == [CLOCK_MS + 11 * SECOND]


def test_a_mute_does_not_disturb_the_match_clock(rig: Rig):
    before = rig.clock()
    rig.mute()
    assert rig.clock() == before == CLOCK_MS
    asyncio.run(rig.hub.advance(CLOCK_MS + SECOND))
    rig.unmute()
    assert rig.clock() == CLOCK_MS + SECOND


def test_a_viewer_who_had_cards_is_told_and_one_who_had_none_is_not(rig: Rig):
    had_cards = rig.sessions.create(CASUAL)
    rig.router.receive(_card(CLOCK_MS - MINUTE, CASUAL))
    rig.queues.release_due(had_cards, CLOCK_MS - MINUTE)
    had_cards = rig.sessions.mark_seen(had_cards.session_id, CLOCK_MS - MINUTE)
    had_none = rig.sessions.create(CASUAL)

    rig.mute()
    rig.queues.release_due(rig.sessions.get(had_cards.session_id), CLOCK_MS)
    rig.queues.release_due(rig.sessions.get(had_none.session_id), CLOCK_MS)

    told = [
        entry for entry in rig.queues.released(had_cards.session_id) if isinstance(entry, Notice)
    ]
    assert told == [Notice(lens_id=CASUAL, kind=NoticeKind.PAUSED, clock_ms=CLOCK_MS)]
    assert [
        entry for entry in rig.queues.released(had_none.session_id) if isinstance(entry, Notice)
    ] == []


# --- the producer view --------------------------------------------------------------------------


def test_the_producer_view_shows_a_muted_lens_and_the_action_that_muted_it(rig: Rig):
    rig.mute(actor="dana")
    snapshot = rig.feed.snapshot()
    muted = next(view for view in snapshot.lenses if view.lens_id == CASUAL)
    assert muted.state is LensState.MUTED
    assert muted.muted is not None
    assert (muted.muted.actor, muted.muted.reason) == ("dana", "named the wrong player")
    assert muted.muted.clock_ms == CLOCK_MS
    others = [view for view in snapshot.lenses if view.lens_id != CASUAL]
    assert others and all(view.state is not LensState.MUTED for view in others)
    assert [action.actor for action in snapshot.actions] == ["dana"]


def test_the_producer_view_stops_showing_the_mute_once_it_is_undone(rig: Rig):
    rig.mute()
    rig.unmute()
    snapshot = rig.feed.snapshot()
    casual = next(view for view in snapshot.lenses if view.lens_id == CASUAL)
    assert casual.state is not LensState.MUTED and casual.muted is None
    assert len(snapshot.actions) == 2  # the log keeps both


def _rendition(lens_id: str, reason) -> Rendition:
    return Rendition(
        rendition_id=f"m:{lens_id}", moment_id="m", lens_id=lens_id, language="en", headline=None,
        body=None, surviving_claim_ids=(), suppressed=True, suppression_reason=reason,
        rendered_at=datetime.now(UTC), model="templates", model_version="t",
    )  # fmt: skip


def test_a_muted_rendition_reads_as_a_lens_a_producer_switched_off(rig: Rig):
    from matchlens.models import MomentType, SuppressionReason
    from matchlens.rendering import LensOutcome, MomentOutcome

    rows = lenses.all_lenses()
    outcome = LensOutcome(
        lens_id=CASUAL, rendition=_rendition(CASUAL, SuppressionReason.MUTED),
        importance=0.4, shown_in_window=0,
    )  # fmt: skip
    rig.feed.receive(
        MomentOutcome(
            moment_id="m",
            clock_ms=CLOCK_MS,
            moment_type=MomentType.CHANCE,
            lens_ids=tuple(lens.lens_id for lens in rows),
            outcomes=(outcome,),
        )  # fmt: skip
    )
    casual = next(view for view in rig.feed.snapshot().lenses if view.lens_id == CASUAL)
    assert casual.state is LensState.QUIET
    assert "producer" in casual.why.lower()


def _blocks(response: httpx.Response) -> Iterator[list[str]]:
    block: list[str] = []
    for line in response.iter_lines():
        if line:
            block.append(line)
        elif block:
            yield block
            block = []


def test_the_producer_stream_shows_a_mute_as_it_happens():
    mutes = Mutes()
    feed = ProducerFeed(lenses.all_lenses(), mutes)
    with (
        LiveServer(MatchStateHub(), producer=feed, mutes=mutes) as live,
        live.client.stream("GET", "/producer/stream") as stream,
    ):
        blocks = _blocks(stream)
        before = json.loads(_fields(next(blocks))["data"])
        assert {row["state"] for row in before["lenses"]} == {"listening"}

        posted = live.client.post(
            "/producer/mute", json={"lens_id": CASUAL, "reason": "named the wrong player"}
        )
        assert posted.status_code == 201

        after = json.loads(_fields(next(blocks))["data"])
    states = {row["lens_id"]: row["state"] for row in after["lenses"]}
    assert states[CASUAL] == "muted"
    assert [action["action"] for action in after["actions"]] == ["suppress"]


# --- the page -----------------------------------------------------------------------------------


def test_the_producer_page_calls_the_controls_and_will_not_send_without_a_reason():
    script = (WEB_DIR / "producer.js").read_text()
    assert "/producer/mute" in script and "/producer/unmute" in script
    assert "reason" in script
    assert "A reason is needed" in script  # the page's own refusal, before any request


def test_every_page_with_a_panel_shows_a_notice_in_the_card_list():
    script = (WEB_DIR / "panel.js").read_text()
    assert 'addEventListener("notice"' in script
    assert "Insights paused" in script and "Insights resumed" in script
