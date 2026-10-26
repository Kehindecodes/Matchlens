"""X4: the public endpoints are limited per client, and a limit is tested, not assumed.

The limiter is plain ASGI in front of the app, so most tests drive it with a stand-in app and a
fake clock. The two that matter most use the real thing: a real uvicorn server, to show a closed
stream gives its slot back, and `apps.delivery.app`, to show the deployed app is the limited one.
"""

import asyncio
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchlens.config.settings import settings
from matchlens.delivery.http import create_app
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.limits import Limiter, LimitsMiddleware
from matchlens.delivery.sessions import SessionStore
from tests.delivery.test_http import LiveServer

ROOM = 10_000  # a limit a test is not about


class Ticker:
    """A clock the test moves."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def _limiter(clock=time.monotonic, **overrides) -> Limiter:
    limits = dict(
        new_sessions_per_min=ROOM,
        changes_per_min=ROOM,
        reads_per_min=ROOM,
        streams_per_client=ROOM,
        streams_total=ROOM,
        trust_forwarded_for=False,
    )
    return Limiter(**{**limits, **overrides}, clock=clock)


def _client(limiter: Limiter, sessions: SessionStore | None = None) -> TestClient:
    app = create_app(
        MatchStateHub(), SessionStore() if sessions is None else sessions, limits=limiter
    )
    return TestClient(app)


# --- requests per client --------------------------------------------------------------------------


def test_a_client_over_its_session_limit_is_refused_and_told_when_to_retry():
    with _client(_limiter(new_sessions_per_min=3)) as client:
        assert [client.post("/session").status_code for _ in range(3)] == [201, 201, 201]
        refused = client.post("/session")
    assert refused.status_code == 429
    assert 1 <= int(refused.headers["retry-after"]) <= 60


def test_the_limit_is_a_sliding_minute_not_a_lockout():
    clock = Ticker()
    with _client(_limiter(clock, new_sessions_per_min=2)) as client:
        assert client.post("/session").status_code == 201
        clock.now += 30
        assert client.post("/session").status_code == 201
        assert client.post("/session").status_code == 429
        clock.now += 31  # the first request is now a minute old, the second is not
        assert client.post("/session").status_code == 201
        assert client.post("/session").status_code == 429


def test_changes_are_counted_apart_from_reads_and_new_sessions():
    with _client(_limiter(changes_per_min=2)) as client:
        assert [client.post("/playback", json={"speed": 5}).status_code for _ in range(2)] == [
            200,
            200,
        ]
        assert client.post("/playback", json={"speed": 5}).status_code == 429
        assert client.post("/ladder", json={"models": "off"}).status_code == 429  # one budget
        assert client.get("/playback").status_code == 200
        assert client.post("/session").status_code == 201


def test_reads_are_limited_too():
    with _client(_limiter(reads_per_min=3)) as client:
        assert [client.get("/lenses").status_code for _ in range(3)] == [200, 200, 200]
        assert client.get("/lenses").status_code == 429
        assert client.post("/session").status_code == 201


# --- who the client is ----------------------------------------------------------------------------


def test_each_client_has_its_own_budget_behind_the_ingress():
    # Every request reaches the app from the ingress's address. Without the forwarded header
    # one visitor's limit would be everyone's, and a second visitor would disturb the first.
    with _client(_limiter(new_sessions_per_min=1, trust_forwarded_for=True)) as client:
        first = {"X-Forwarded-For": "198.51.100.1"}
        second = {"X-Forwarded-For": "198.51.100.2"}
        assert client.post("/session", headers=first).status_code == 201
        assert client.post("/session", headers=first).status_code == 429
        assert client.post("/session", headers=second).status_code == 201


def test_a_client_cannot_buy_a_new_budget_by_writing_its_own_forwarded_address():
    # The ingress appends the address it saw and nothing else; whatever is to its left came from
    # the client (Container Apps, "Ingress": only the rightmost IP is provided by the platform).
    with _client(_limiter(new_sessions_per_min=1, trust_forwarded_for=True)) as client:
        assert (
            client.post("/session", headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 201
        )
        spoofed = {"X-Forwarded-For": "1.2.3.4, 203.0.113.9"}
        assert client.post("/session", headers=spoofed).status_code == 429


def test_the_forwarded_header_is_ignored_unless_it_is_trusted():
    # Run directly, nothing sits in front of the app, so the header is whatever the client wrote.
    with _client(_limiter(new_sessions_per_min=1)) as client:
        assert (
            client.post("/session", headers={"X-Forwarded-For": "198.51.100.1"}).status_code == 201
        )
        assert (
            client.post("/session", headers={"X-Forwarded-For": "198.51.100.2"}).status_code == 429
        )


def test_clients_whose_window_has_passed_are_forgotten():
    clock = Ticker()
    limiter = _limiter(clock, new_sessions_per_min=1, trust_forwarded_for=True)
    with _client(limiter) as client:
        for last in range(50):
            client.post("/session", headers={"X-Forwarded-For": f"198.51.100.{last}"})
        assert limiter.tracked_clients == 50
        clock.now += 61
        client.post("/session", headers={"X-Forwarded-For": "198.51.100.200"})
    assert limiter.tracked_clients == 1


# --- open streams ---------------------------------------------------------------------------------


async def _call(app, path: str, *, client: str = "10.0.0.1", method: str = "GET") -> int:
    """One request through `app`; its status."""
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "method": method, "path": path, "headers": [], "client": (client, 5000),
    }  # fmt: skip
    await app(scope, receive, send)
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def _holding(gate: asyncio.Event):
    """An app that answers 200 once `gate` is set: a stream that stays open until then."""

    async def app(scope, receive, send):
        await gate.wait()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return app


def test_a_client_over_its_open_streams_is_refused_and_a_closed_stream_frees_its_slot():
    async def scenario():
        gate = asyncio.Event()
        app = LimitsMiddleware(_holding(gate), _limiter(streams_per_client=2))
        open_two = [asyncio.create_task(_call(app, "/stream")) for _ in range(2)]
        await asyncio.sleep(0)
        assert await _call(app, "/stream") == 429
        gate.set()
        assert await asyncio.gather(*open_two) == [200, 200]
        assert await _call(app, "/stream") == 200

    asyncio.run(scenario())


def test_a_stream_cancelled_mid_flight_gives_its_slot_back():
    async def scenario():
        gate = asyncio.Event()
        app = LimitsMiddleware(_holding(gate), _limiter(streams_per_client=1))
        held = asyncio.create_task(_call(app, "/stream"))
        await asyncio.sleep(0)
        assert await _call(app, "/stream") == 429
        held.cancel()
        await asyncio.gather(held, return_exceptions=True)
        gate.set()
        assert await _call(app, "/stream") == 200

    asyncio.run(scenario())


def test_the_whole_server_has_a_ceiling_on_open_streams_whoever_asks():
    async def scenario():
        gate = asyncio.Event()
        app = LimitsMiddleware(_holding(gate), _limiter(streams_total=2))
        held = [asyncio.create_task(_call(app, "/stream", client=f"10.0.0.{n}")) for n in (1, 2)]
        await asyncio.sleep(0)
        busy = await _call(app, "/stream", client="10.0.0.3")
        gate.set()
        await asyncio.gather(*held)
        return busy

    assert asyncio.run(scenario()) == 503


def test_the_producer_stream_counts_as_a_stream():
    async def scenario():
        gate = asyncio.Event()
        app = LimitsMiddleware(_holding(gate), _limiter(streams_per_client=1))
        held = asyncio.create_task(_call(app, "/stream"))
        await asyncio.sleep(0)
        refused = await _call(app, "/producer/stream")
        gate.set()
        await held
        return refused

    assert asyncio.run(scenario()) == 429


def test_a_refused_stream_costs_the_client_nothing_it_can_not_get_back():
    async def scenario():
        gate = asyncio.Event()
        app = LimitsMiddleware(_holding(gate), _limiter(streams_per_client=1))
        held = asyncio.create_task(_call(app, "/stream"))
        await asyncio.sleep(0)
        for _ in range(5):
            assert await _call(app, "/stream") == 429
        gate.set()
        await held
        assert await _call(app, "/stream") == 200

    asyncio.run(scenario())


@pytest.fixture
def limited_live() -> Iterator[LiveServer]:
    with LiveServer(MatchStateHub(), limits=_limiter(streams_per_client=1)) as server:
        yield server


def test_on_a_real_server_a_closed_browser_tab_gives_its_stream_slot_back(limited_live):
    first, second = limited_live.session(), limited_live.session()
    with limited_live.client.stream("GET", f"/stream?session_id={first}") as open_stream:
        assert open_stream.status_code == 200
        with limited_live.client.stream("GET", f"/stream?session_id={second}") as refused:
            assert refused.status_code == 429
    deadline = time.monotonic() + 5
    while True:  # the server notices the disconnect on its own time
        with limited_live.client.stream("GET", f"/stream?session_id={second}") as retry:
            if retry.status_code == 200 or time.monotonic() > deadline:
                break
        time.sleep(0.05)
    assert retry.status_code == 200


# --- the number of sessions -----------------------------------------------------------------------


def test_a_full_session_store_refuses_new_sessions_and_leaves_the_others_working():
    with _client(_limiter(), SessionStore(max_sessions=2)) as client:
        made = [client.post("/session") for _ in range(2)]
        full = client.post("/session")
        assert full.status_code == 503
        assert int(full.headers["retry-after"]) >= 1
        assert client.get(f"/session/{made[0].json()['session_id']}").status_code == 200


# --- the deployed app -----------------------------------------------------------------------------


def test_the_deployed_app_is_the_limited_one():
    from apps import delivery

    client = TestClient(delivery.app)  # no `with`: the feed is not started
    statuses = [
        client.post("/session").status_code for _ in range(settings.limit_new_sessions_per_min + 1)
    ]
    assert statuses[:-1] == [201] * settings.limit_new_sessions_per_min
    assert statuses[-1] == 429


def test_the_stack_tells_the_app_to_trust_the_ingress_address():
    # Without it the app sees the ingress for every visitor and one limit is everyone's.
    bicep = (Path(__file__).parents[2] / "infra" / "main.bicep").read_text()
    assert "MATCHLENS_TRUST_FORWARDED_FOR" in bicep
