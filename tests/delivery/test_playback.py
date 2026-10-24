"""D3: speed for the judge path, and watching from kickoff (D33).

The feed runs for real, but on virtual wall time: `asyncio.sleep` advances a clock the replay
reads, so a full match at 25x and ten minutes at 1x take seconds and replay the same way every
time. One slow test does it on real time, for the figure J1 quotes.
"""

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from apps import pipeline
from apps.delivery import run_local_feed
from matchlens.config import settings
from matchlens.delivery.http import create_app
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.models import ViewerSession
from matchlens.rendering import Card
from matchlens.source import MatchSetup, simulate
from matchlens.source.replay import Replay
from tests.delivery.test_http import LiveServer, _fields
from tests.delivery.test_release import _card

SECOND = 1_000
MINUTE = 60 * SECOND
FAR = 45 * SECOND
J1_LIMIT_S = 5 * 60
ITEMS = list(simulate(settings.match_seed))  # generated once; every run replays the same match


# --- the speed: one for the match, changed from the page, refused when wrong --------------------


@pytest.fixture
def hub() -> MatchStateHub:
    return MatchStateHub()


@pytest.fixture
def client(hub: MatchStateHub):
    with TestClient(create_app(hub, SessionStore())) as c:
        yield c


def test_the_page_can_read_the_speed_and_the_live_clock(client: TestClient):
    playback = client.get("/playback").json()
    assert playback == {"speed": None, "clock_ms": -1, "max_speed": settings.max_replay_speed}


def test_a_speed_is_changed_without_a_redeploy(client: TestClient, hub: MatchStateHub):
    r = client.post("/playback", json={"speed": 5})
    assert r.status_code == 200
    assert r.json()["speed"] == 5
    assert hub.speed == 5


@pytest.mark.parametrize("speed", [0, -1, settings.max_replay_speed + 1, "fast", None])
def test_an_invalid_speed_is_refused_not_defaulted(client: TestClient, hub: MatchStateHub, speed):
    client.post("/playback", json={"speed": 25})
    assert client.post("/playback", json={"speed": speed}).status_code == 422
    assert client.post("/playback", json={}).status_code == 422
    assert hub.speed == 25


def test_an_open_stream_is_told_the_speed_when_it_changes():
    hub, queues = MatchStateHub(), ReleaseQueues()
    with LiveServer(hub, queues) as live:
        session_id = live.session()
        assert live.loop is not None
        asyncio.run_coroutine_threadsafe(hub.set_speed(5), live.loop).result(timeout=5)
        [block] = live.events(session_id, 1)
    fields = _fields(block)
    assert fields["event"] == "playback"
    assert "id" not in fields  # it is not a place in the stream, so it does not move Last-Event-ID
    assert json.loads(fields["data"]) == {"speed": 5}


# --- joining late, and watching from kickoff (D33) -----------------------------------------------


def _router() -> tuple[SessionStore, ReleaseQueues, CardRouter]:
    sessions, queues = SessionStore(), ReleaseQueues()
    return sessions, queues, CardRouter(sessions, queues)


def test_a_late_joiner_is_given_the_cards_its_video_has_not_reached():
    sessions, queues, router = _router()
    for clock in (60 * MINUTE, 67 * MINUTE + 30 * SECOND, 67 * MINUTE + 50 * SECOND):
        router.receive(_card(clock))
    now = 68 * MINUTE
    late = sessions.create(stream_offset_ms=FAR)  # its video is at 67:15
    router.join(late, now)
    assert queues.depth(late.session_id) == 2
    released = queues.release_due(late, now + 40 * SECOND)
    assert [c.display_at_clock for c in released] == [
        67 * MINUTE + 30 * SECOND,
        67 * MINUTE + 50 * SECOND,
    ]


def test_a_joiner_is_not_given_what_its_video_has_passed_or_another_lens():
    sessions, queues, router = _router()
    router.receive(_card(10 * SECOND))
    router.receive(_card(50 * SECOND, lens_id="other_lens"))
    viewer = sessions.create(stream_offset_ms=0)
    router.join(viewer, 60 * SECOND)
    assert queues.depth(viewer.session_id) == 0


def test_watching_from_kickoff_is_given_every_card_and_releases_them_from_0_00():
    sessions, queues, router = _router()
    clocks = [m * MINUTE for m in (3, 20, 41, 77, 90)]
    for clock in clocks:
        router.receive(_card(clock))
    now = 92 * MINUTE
    judge = sessions.create(stream_offset_ms=now)
    router.join(judge, now)
    assert queues.release_due(judge, now) == []  # their video is at 0:00
    assert [c.display_at_clock for c in queues.release_due(judge, now + 21 * MINUTE)] == clocks[:2]


def test_watching_from_kickoff_leaves_everyone_else_where_they_were():
    sessions, queues, router = _router()
    live = sessions.create()
    router.receive(_card(SECOND))
    assert len(queues.release_due(live, SECOND)) == 1
    judge = sessions.create(stream_offset_ms=2 * SECOND)
    router.join(judge, 2 * SECOND)
    assert queues.depth(judge.session_id) == 1
    assert queues.depth(live.session_id) == 0
    assert queues.count_released(live.session_id) == 1


def test_a_session_made_over_http_is_given_the_cards_it_has_not_reached(hub: MatchStateHub):
    sessions, queues = SessionStore(), ReleaseQueues()
    router = CardRouter(sessions, queues)
    router.receive(_card(30 * SECOND))
    with TestClient(create_app(hub, sessions, queues, router)) as c:
        made = c.post("/session", json={"stream_offset_ms": 10 * SECOND}).json()
    assert queues.depth(made["session_id"]) == 1


# --- the feed on virtual wall time ---------------------------------------------------------------


class VirtualTime:
    """Wall time that passes only when the feed sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self._real_sleep = asyncio.sleep

    def time(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += max(seconds, 0.0)
        for _ in range(5):  # let the woken streams run before the feed's next step
            await self._real_sleep(0)


Release = tuple[float, int, Card]  # (virtual wall seconds, hub clock, card)


def _play(
    monkeypatch: pytest.MonkeyPatch,
    speed: float,
    until_ms: int | None,
    offsets: tuple[int, ...],
    change: tuple[float, float] | None = None,
) -> tuple[Replay, dict[int, list[Release]], float]:
    """Run the feed on virtual time with a viewer at each offset; their releases, keyed by offset.

    `change` is (virtual seconds, speed): a page asks for that speed at that moment.
    """
    vt = VirtualTime()
    monkeypatch.setattr(asyncio, "sleep", vt.sleep)
    items = ITEMS
    if until_ms is not None:
        items = [i for i in ITEMS if isinstance(i, MatchSetup) or i.clock_ms <= until_ms]
    replay = Replay(items, speed=speed, now=vt.time)
    hub, (sessions, queues, router) = MatchStateHub(), _router()
    viewers = [sessions.create(stream_offset_ms=o) for o in offsets]
    releases: dict[int, list[Release]] = {o: [] for o in offsets}
    finished_at: list[float] = []

    async def watch(viewer: ViewerSession) -> None:
        async for clock_ms in hub.ticks():
            for card in queues.release_due(viewer, clock_ms):
                releases[viewer.stream_offset_ms].append((vt.now, clock_ms, card))
            if replay.finished and clock_ms > replay.duration_ms + viewer.stream_offset_ms:
                return

    async def run() -> None:
        feed = asyncio.create_task(run_local_feed(hub, replay, pipeline.Pipeline(), router.receive))
        watchers = [asyncio.create_task(watch(v)) for v in viewers]
        while not replay.finished:
            if change is not None and vt.now >= change[0] and hub.speed != change[1]:
                await hub.set_speed(change[1])
            await vt.sleep(0)
        finished_at.append(vt.now)
        await asyncio.gather(*watchers)
        feed.cancel()

    asyncio.run(run())
    return replay, releases, finished_at[0]


def _assert_release_rule(releases: dict[int, list[Release]]) -> None:
    for offset, log in releases.items():
        clocks = [card.display_at_clock for _, _, card in log]
        assert clocks == sorted(clocks)  # display_at_clock order
        for _, hub_clock, card in log:
            assert card.display_at_clock <= hub_clock - offset  # never early (D1)


@pytest.fixture(scope="module")
def demo_speed_run():
    with pytest.MonkeyPatch.context() as mp:
        return _play(mp, settings.replay_speed, None, (0, FAR))


def test_a_full_match_plays_in_under_five_minutes_at_the_demo_speed(demo_speed_run):
    replay, releases, finished_at = demo_speed_run
    assert finished_at < J1_LIMIT_S  # J1: about 227 s of wall time at 25x
    assert finished_at == pytest.approx(replay.duration_ms / 1000 / settings.replay_speed, abs=1)
    assert releases[0] and len(releases[0]) == len(releases[FAR])


def test_the_release_rule_holds_at_the_demo_speed(demo_speed_run):
    _, releases, _ = demo_speed_run
    _assert_release_rule(releases)


def test_the_gap_between_two_cards_scales_with_the_speed(demo_speed_run):
    _, releases, _ = demo_speed_run
    log = releases[0]
    for (wall_a, _, a), (wall_b, _, b) in zip(log, log[1:], strict=False):
        match_gap_s = (b.display_at_clock - a.display_at_clock) / 1000
        # Released on the first state at or after each card: a match second at most, either side.
        assert wall_b - wall_a == pytest.approx(
            match_gap_s / settings.replay_speed, abs=2 / settings.replay_speed
        )


def test_the_release_rule_holds_at_1x(monkeypatch: pytest.MonkeyPatch):
    _, releases, finished_at = _play(monkeypatch, 1.0, 10 * MINUTE, (0, FAR))
    assert finished_at == pytest.approx(10 * 60, abs=1)  # ten match minutes take ten minutes
    _assert_release_rule(releases)


def test_a_speed_change_mid_match_is_taken_up_and_skips_or_repeats_nothing(
    monkeypatch: pytest.MonkeyPatch, demo_speed_run
):
    replay, changed, finished_at = _play(
        monkeypatch, 25.0, 10 * MINUTE, (FAR,), change=(5 * 60 / 25, 5.0)
    )
    assert replay.speed == 5.0
    # Five match minutes at 25x, then five at 5x.
    assert finished_at == pytest.approx(5 * 60 / 25 + 5 * 60 / 5, abs=1)
    # The pipeline only looks back, so the first ten minutes' cards are the full match's.
    _, steady, _ = demo_speed_run
    expected = [
        c.rendition.rendition_id for _, _, c in steady[FAR] if c.display_at_clock <= 10 * MINUTE
    ]
    assert [c.rendition.rendition_id for _, _, c in changed[FAR]] == expected
    _assert_release_rule(changed)


# --- J1 on real time -----------------------------------------------------------------------------


@pytest.mark.slow
def test_j1_a_full_match_on_real_time_at_the_demo_speed():
    """The figure the submission quotes. About four minutes; run with `pytest -m slow`."""
    replay = Replay.from_seed(settings.match_seed, speed=settings.replay_speed)
    hub, (_, _, router) = MatchStateHub(), _router()

    async def run() -> float:
        start = time.monotonic()
        feed = asyncio.create_task(run_local_feed(hub, replay, pipeline.Pipeline(), router.receive))
        while not replay.finished:
            await asyncio.sleep(0.05)
        feed.cancel()
        return time.monotonic() - start

    took = asyncio.run(run())
    print(f"J1: seed {settings.match_seed} at {settings.replay_speed}x took {took:.1f} s")
    assert took < J1_LIMIT_S
