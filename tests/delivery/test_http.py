"""S3: the page, viewer sessions, and the SSE stream."""

import asyncio
import json
import threading
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import fastapi.routing
import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from apps.delivery import run_local_feed
from apps.pipeline import Pipeline
from matchlens.delivery.http import create_app
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.sessions import SessionStore
from matchlens.models import Frame, MomentType, Phase, Rendition
from matchlens.rendering import Card
from matchlens.source import MatchSetup, simulate
from matchlens.source.replay import Replay
from matchlens.understanding.match_state import MatchState, TeamScore
from tests.overlays import overlay_for


def _state(seq: int, clock_ms: int = 0) -> MatchState:
    return MatchState(
        seq=seq, clock_ms=clock_ms, period=1,
        score=(TeamScore(team_id="h", short_name="HOM", goals=0),
               TeamScore(team_id="a", short_name="AWY", goals=0)),
    )  # fmt: skip


@pytest.fixture
def hub() -> MatchStateHub:
    return MatchStateHub()


@pytest.fixture
def client(hub: MatchStateHub) -> Iterator[TestClient]:
    with TestClient(create_app(hub, SessionStore())) as c:
        yield c


class LiveServer:
    """The app on a real uvicorn server in a thread, so streams disconnect as a browser's do."""

    def __init__(self, hub: MatchStateHub, queues: ReleaseQueues):
        self.hub = hub
        self.sessions = SessionStore()
        self.loop: asyncio.AbstractEventLoop | None = None

        @asynccontextmanager
        async def lifespan(_):
            self.loop = asyncio.get_running_loop()
            yield

        config = uvicorn.Config(
            create_app(hub, self.sessions, queues, lifespan=lifespan),
            host="127.0.0.1", port=0, log_level="warning", timeout_graceful_shutdown=1,
        )  # fmt: skip
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> "LiveServer":
        self.thread.start()
        while not self.server.started:
            time.sleep(0.01)
        port = self.server.servers[0].sockets[0].getsockname()[1]
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5)
        return self

    def __exit__(self, *exc) -> None:
        self.client.close()
        self.server.should_exit = True
        self.thread.join(timeout=5)

    def publish(self, state: MatchState) -> None:
        assert self.loop is not None
        asyncio.run_coroutine_threadsafe(self.hub.publish(state), self.loop).result(timeout=5)

    def session(self) -> str:
        return self.client.post("/session").json()["session_id"]

    def events(self, session_id: str, n: int, last_event_id: str | None = None) -> list[list[str]]:
        """The first `n` SSE blocks (events or comments) from the stream, then disconnect."""
        headers = {} if last_event_id is None else {"Last-Event-ID": last_event_id}
        blocks: list[list[str]] = []
        current: list[str] = []
        url = f"/stream?session_id={session_id}"
        with self.client.stream("GET", url, headers=headers) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            for line in r.iter_lines():
                if line:
                    current.append(line)
                    continue
                if current:
                    blocks.append(current)
                    current = []
                if len(blocks) == n:
                    break
        return blocks


@pytest.fixture
def queues() -> ReleaseQueues:
    return ReleaseQueues()


@pytest.fixture
def live(hub: MatchStateHub, queues: ReleaseQueues) -> Iterator[LiveServer]:
    with LiveServer(hub, queues) as server:
        yield server


def _fields(block: list[str]) -> dict[str, str]:
    return dict(line.split(": ", 1) for line in block if not line.startswith(":"))


def _new_session(client: TestClient, **body) -> dict:
    r = client.post("/session", json=body or None)
    assert r.status_code == 201
    return r.json()


# --- the page -------------------------------------------------------------------------------------


def test_the_page_is_served(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert "<title>MatchLens</title>" in r.text
    assert client.get("/static/app.js").status_code == 200


def test_the_delay_view_is_served(client: TestClient):
    r = client.get("/delay")
    assert r.status_code == 200
    assert "delay.js" in r.text
    assert client.get("/static/delay.js").status_code == 200


# --- sessions -------------------------------------------------------------------------------------


def test_a_session_with_no_lens_gets_whole_match_casual(client: TestClient):
    assert _new_session(client)["lens_id"] == "match_casual"


def test_a_session_keeps_its_lens_across_a_reload(client: TestClient):
    created = _new_session(client, lens_id="team_engaged", focus_team="h")
    again = client.get(f"/session/{created['session_id']}").json()
    assert again == created


def test_two_tabs_get_two_independent_sessions(client: TestClient):
    a, b = _new_session(client), _new_session(client)
    assert a["session_id"] != b["session_id"]


def test_an_unknown_session_is_not_found(client: TestClient):
    assert client.get("/session/nope").status_code == 404
    assert client.get("/stream?session_id=nope").status_code == 404


# --- the stream -----------------------------------------------------------------------------------


def test_the_stream_sends_the_latest_state_with_an_id(live: LiveServer):
    session = live.session()
    live.publish(_state(seq=7, clock_ms=61_000))
    [block] = live.events(session, 1)
    fields = _fields(block)
    assert fields["event"] == "match_state"
    assert fields["id"] == "7:0"  # the state's seq, and no card released yet
    assert json.loads(fields["data"])["clock_ms"] == 61_000


def test_a_reconnect_resumes_from_last_event_id_without_replaying(live: LiveServer):
    session = live.session()
    live.publish(_state(seq=7))
    [first] = live.events(session, 1)
    assert _fields(first)["id"] == "7:0"

    # Reconnect having seen 7: nothing is resent until a newer state arrives.
    threading.Timer(0.3, live.publish, (_state(seq=9),)).start()
    [resumed] = live.events(session, 1, last_event_id="7:0")
    assert _fields(resumed)["id"] == "9:0"


def test_an_idle_stream_gets_a_keepalive(live: LiveServer, monkeypatch: pytest.MonkeyPatch):
    # FastAPI sends a keepalive comment every 15 s of silence; shorten it so the test is quick.
    monkeypatch.setattr(fastapi.routing, "_PING_INTERVAL", 0.2)
    [block] = live.events(live.session(), 1)
    assert all(line.startswith(":") for line in block)


def test_a_released_card_is_streamed_after_the_clock(live: LiveServer, queues: ReleaseQueues):
    session_id = live.session()
    session = live.sessions.get(session_id)
    rendition = Rendition(
        rendition_id="m:l", moment_id="m", lens_id=session.lens_id, language="en",
        headline="The walking skeleton", body="b", surviving_claim_ids=(), suppressed=False,
        suppression_reason=None, rendered_at=datetime.now(UTC),
    )  # fmt: skip
    queues.enqueue(
        Card(
            rendition=rendition,
            display_at_clock=4_032_000,
            moment_type=MomentType.CHANCE,
            importance=0.5,
            body_in_full="b",
            overlay=overlay_for(rendition, 4_032_000),
        ),
        session,
    )
    live.publish(_state(seq=7, clock_ms=4_033_000))
    state, card = live.events(session_id, 2)
    assert _fields(state)["event"] == "match_state"
    fields = _fields(card)
    assert fields["event"] == "card" and fields["id"] == "7:1"
    data = json.loads(fields["data"])
    assert data["display_at_clock"] == 4_032_000
    assert data["rendition"]["headline"] == "The walking skeleton"


# --- the local feed -------------------------------------------------------------------------------


def test_the_local_feed_publishes_a_ticking_clock():
    setup = next(iter(simulate(1)))  # just the roster; the match is not generated
    assert isinstance(setup, MatchSetup)
    frames = [
        Frame(
            seq=i, clock_ms=i * 500, period=1, phase=Phase.IN_PLAY, ball_x=0.0, ball_y=0.0,
            ball_z=0.0, ball_speed=0.0, carrier=None, players=(),
        )
        for i in range(12)
    ]  # fmt: skip
    hub = MatchStateHub()
    replay = Replay([setup, *frames], speed=50.0)

    async def run() -> list[int]:
        feed = asyncio.create_task(run_local_feed(hub, replay, Pipeline(), lambda card: None))
        clocks = [state.clock_ms async for state in _take(hub.follow(), 5)]
        feed.cancel()
        return clocks

    assert asyncio.run(run()) == [0, 1_000, 2_000, 3_000, 4_000]  # one state per match second


async def _take(states, n: int):
    async for state in states:
        yield state
        n -= 1
        if n == 0:
            return
