"""Entrypoint for the delivery container: `uvicorn apps.delivery:app`.

Until the pipeline publishes over Service Bus (S5), the pipeline's side runs in this process: a
seeded replay paced by `settings.replay_speed`, turned into `MatchState` and published to the hub.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from matchlens.config.settings import settings
from matchlens.delivery.http import create_app
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.source.replay import Replay
from matchlens.understanding.match_state import MatchStateTracker

_MAX_NAP_S = 0.25


async def run_local_feed(hub: MatchStateHub, replay: Replay) -> None:
    """Play `replay` in real time and publish a `MatchState` each new match second."""
    tracker = MatchStateTracker(replay.setup)
    replay.play()
    while not replay.finished:
        for item in replay.poll():
            state = tracker.observe(item)
            if state is not None:
                await hub.publish(state)
        wait = replay.next_due_in()
        await asyncio.sleep(_MAX_NAP_S if wait is None else min(wait, _MAX_NAP_S))


hub = MatchStateHub()
sessions = SessionStore()
queues = ReleaseQueues()
router = CardRouter(
    sessions, queues
)  # Delivery's end of the bus: the pipeline publishes to receive


@asynccontextmanager
async def _lifespan(_: FastAPI):
    replay = Replay.from_seed(settings.match_seed, speed=settings.replay_speed)
    feed = asyncio.create_task(run_local_feed(hub, replay))
    try:
        yield
    finally:
        feed.cancel()


app = create_app(hub, sessions, queues, lifespan=_lifespan)
