"""Entrypoint for the delivery container: `uvicorn apps.delivery:app`.

Until the pipeline publishes over Service Bus (S5), the pipeline's side runs in this process: a
seeded replay paced by `settings.replay_speed` drives both the clock (`MatchState`, to the hub)
and the pipeline, whose cards go to Delivery's end of the bus, `router.receive`.
"""

import asyncio
from contextlib import asynccontextmanager

from azure.monitor.opentelemetry import configure_azure_monitor
from fastapi import FastAPI

from apps.pipeline import Pipeline, Publish
from matchlens.config.settings import settings
from matchlens.delivery.http import create_app
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.explanation import foundry
from matchlens.rendering import Card
from matchlens.source.replay import Replay
from matchlens.understanding.match_state import MatchStateTracker

_MAX_NAP_S = 0.25


async def run_local_feed(
    hub: MatchStateHub, replay: Replay, pipeline: Pipeline, publish: Publish
) -> None:
    """Play `replay` in real time: a `MatchState` each match second, and the pipeline's cards.

    Runs until cancelled: after the last item it goes on advancing the hub's clock.
    """
    tracker = MatchStateTracker(replay.setup)
    pipeline.process(replay.setup)
    await hub.set_speed(replay.speed)
    replay.play()
    while not replay.finished:
        _follow_speed(hub, replay)
        for item in replay.poll():
            for card in pipeline.process(item):
                publish(card)
            state = tracker.observe(item)
            if state is not None:
                await hub.publish(state)
        wait = replay.next_due_in()
        await asyncio.sleep(_MAX_NAP_S if wait is None else min(wait, _MAX_NAP_S))
    # The last state is the final whistle, but a viewer behind the action is still watching:
    # keep the clock running so the cards they are owed are released when they reach them.
    while True:
        _follow_speed(hub, replay)
        await hub.advance(int(replay.position_ms))
        await asyncio.sleep(_MAX_NAP_S)


def _follow_speed(hub: MatchStateHub, replay: Replay) -> None:
    """Take up a speed a page asked for. The replay rebases, so no match time is skipped."""
    if hub.speed is not None and hub.speed != replay.speed:
        replay.set_speed(hub.speed)


hub = MatchStateHub()
sessions = SessionStore()
queues = ReleaseQueues()
router = CardRouter(
    sessions, queues
)  # Delivery's end of the bus: the pipeline publishes to receive


@asynccontextmanager
async def _lifespan(_: FastAPI):
    if settings.appinsights_connection_string:
        configure_azure_monitor(connection_string=settings.appinsights_connection_string)
    replay = Replay.from_seed(settings.match_seed, speed=settings.replay_speed)
    loop = asyncio.get_running_loop()
    proposer = foundry.from_settings()

    def publish(card: Card) -> None:
        # A card the editorial thread finishes is handed to the release queues on this loop.
        loop.call_soon_threadsafe(router.receive, card)

    pipeline = Pipeline(proposer, publish, writer=proposer)  # one model: A2 and A4 (Q38)
    foundry.warm(proposer)
    feed = asyncio.create_task(run_local_feed(hub, replay, pipeline, router.receive))
    try:
        yield
    finally:
        feed.cancel()
        pipeline.close()


app = create_app(hub, sessions, queues, router, lifespan=_lifespan)
