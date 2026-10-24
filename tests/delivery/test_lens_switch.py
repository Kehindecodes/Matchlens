"""L5: switching lens mid-match. One POST, the stream stays open, the next card is the new lens."""

import json
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from matchlens import lenses
from matchlens.delivery.http import create_app
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.sessions import SessionStore
from matchlens.models import MomentType, Rendition, Scope
from matchlens.rendering import Card
from tests.delivery.test_http import LiveServer, _fields, _state
from tests.overlays import overlay_for

MATCH = [lens for lens in lenses.all_lenses() if lens.scope is Scope.MATCH]
TEAM = next(lens for lens in lenses.all_lenses() if lens.scope is Scope.TEAM)
FIRST, SECOND = MATCH[0], MATCH[1]


@pytest.fixture
def sessions() -> SessionStore:
    return SessionStore()


@pytest.fixture
def client(sessions: SessionStore) -> Iterator[TestClient]:
    with TestClient(create_app(MatchStateHub(), sessions)) as c:
        yield c


def _start(client: TestClient, lens_id: str = FIRST.lens_id) -> str:
    return client.post("/session", json={"lens_id": lens_id}).json()["session_id"]


def _switch(client, session_id: str, lens_id: str, focus_team: str | None = None):
    return client.post(
        f"/session/{session_id}/lens", json={"lens_id": lens_id, "focus_team": focus_team}
    )


# --- the switch -----------------------------------------------------------------------------------


def test_a_switch_moves_the_session_to_the_new_lens(client: TestClient):
    session_id = _start(client)
    r = _switch(client, session_id, SECOND.lens_id)
    assert r.status_code == 200
    assert r.json()["lens_id"] == SECOND.lens_id
    assert client.get(f"/session/{session_id}").json()["lens_id"] == SECOND.lens_id


def test_a_switch_to_an_unknown_lens_is_refused_and_changes_nothing(client: TestClient):
    session_id = _start(client)
    before = client.get(f"/session/{session_id}").json()
    assert _switch(client, session_id, "no_such_lens").status_code == 422
    assert client.get(f"/session/{session_id}").json() == before


def test_a_team_lens_needs_a_team_and_leaving_it_clears_the_team(client: TestClient):
    session_id = _start(client)
    before = client.get(f"/session/{session_id}").json()
    assert _switch(client, session_id, TEAM.lens_id).status_code == 422
    assert client.get(f"/session/{session_id}").json() == before

    on_team = _switch(client, session_id, TEAM.lens_id, TEAM.focus_team).json()
    assert on_team["focus_team"] == TEAM.focus_team
    off_team = _switch(client, session_id, FIRST.lens_id, TEAM.focus_team).json()
    assert off_team["focus_team"] is None


def test_an_unknown_session_cannot_switch(client: TestClient):
    assert _switch(client, "nobody", SECOND.lens_id).status_code == 404


def test_a_switch_changes_the_lens_and_nothing_else_about_the_viewer(sessions: SessionStore):
    session = sessions.create(FIRST.lens_id)
    moved = sessions.switch_lens(session.session_id, SECOND.lens_id)
    unchanged = {"lens_id", "focus_team"}
    assert moved.model_dump(exclude=unchanged) == session.model_dump(exclude=unchanged)


# --- the open stream ------------------------------------------------------------------------------


def _card(lens_id: str, moment_id: str, clock_ms: int) -> Card:
    rendition = Rendition(
        rendition_id=f"{moment_id}:{lens_id}", moment_id=moment_id, lens_id=lens_id,
        language="en", headline=moment_id, body="b", surviving_claim_ids=(), suppressed=False,
        suppression_reason=None, rendered_at=datetime.now(UTC),
    )  # fmt: skip
    return Card(
        rendition=rendition,
        display_at_clock=clock_ms,
        moment_type=MomentType.CHANCE,
        importance=0.5,
        body_in_full="b",
        overlay=overlay_for(rendition, clock_ms),
    )


@pytest.fixture
def queues() -> ReleaseQueues:
    return ReleaseQueues()


@pytest.fixture
def live(queues: ReleaseQueues) -> Iterator[LiveServer]:
    with LiveServer(MatchStateHub(), queues) as server:
        yield server


def test_the_stream_stays_open_and_the_next_card_is_the_last_lens_picked(
    live: LiveServer, queues: ReleaseQueues
):
    session_id = live.client.post("/session", json={"lens_id": FIRST.lens_id}).json()["session_id"]
    queues.enqueue(_card(FIRST.lens_id, "before", 60_000), live.sessions.get(session_id))
    live.publish(_state(seq=1, clock_ms=61_000))

    blocks: list[list[str]] = []
    reader = threading.Thread(target=lambda: blocks.extend(live.events(session_id, 4)))
    reader.start()
    time.sleep(0.5)  # the first state and card are out; the same connection carries on below

    # Two switches in quick succession, with a card held for the lens in between.
    assert _switch(live.client, session_id, SECOND.lens_id).status_code == 200
    queues.enqueue(_card(SECOND.lens_id, "skipped", 62_000), live.sessions.get(session_id))
    assert _switch(live.client, session_id, FIRST.lens_id).status_code == 200
    queues.enqueue(_card(FIRST.lens_id, "after", 63_000), live.sessions.get(session_id))
    live.publish(_state(seq=2, clock_ms=64_000))
    reader.join(timeout=5)

    events = [_fields(b)["event"] for b in blocks]
    assert events == ["match_state", "card", "match_state", "card"]
    cards = [json.loads(_fields(b)["data"])["rendition"]["moment_id"] for b in blocks[1::2]]
    assert cards == ["before", "after"]  # nothing retracted, repeated or reordered


def test_the_viewer_page_is_served(client: TestClient):
    r = client.get("/watch")
    assert r.status_code == 200
    assert "/static/watch.js" in r.text
