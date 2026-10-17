"""S4: the skeleton walks. One hardcoded moment from a seed to a viewer session.

`apps.pipeline.run(seed, publish)` runs the seeded match through the pipeline stages and hands
each `Card` to `publish`, which stands in for Service Bus. Delivery's end is `CardRouter.receive`.

The two call-path criteria (all fourteen components entered, nothing bypassed) are Kehinde's
(D20) and are deliberately absent. `matchlens.calltrace.recording()` collects what they need.
"""

import pytest

from apps import pipeline
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.rendering import SKELETON_BODY, SKELETON_HEADLINE, Card
from matchlens.spotting import SKELETON_CLOCK_MS


@pytest.fixture(scope="module")
def walked():
    """Seed 1 end to end: a session on the default lens, then what Delivery releases to it."""
    sessions, queues = SessionStore(), ReleaseQueues()
    session = sessions.create()
    pipeline.run(1, CardRouter(sessions, queues).receive)
    return session, queues.release_due(session, SKELETON_CLOCK_MS)


def test_a_seeded_match_delivers_the_card_to_a_session(walked):
    session, released = walked
    [card] = released
    assert isinstance(card, Card)
    assert card.rendition.lens_id == session.lens_id
    assert (card.rendition.headline, card.rendition.body) == (SKELETON_HEADLINE, SKELETON_BODY)
    assert not card.rendition.suppressed


def test_the_card_is_at_the_hardcoded_match_clock(walked):
    _, [card] = walked
    assert SKELETON_CLOCK_MS <= card.display_at_clock < SKELETON_CLOCK_MS + 10_000
