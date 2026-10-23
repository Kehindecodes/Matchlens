from datetime import UTC, datetime

from matchlens import calltrace, lenses
from matchlens.config import settings
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.models import Rendition
from matchlens.rendering import Card


def _card(lens_id: str = "match_casual", clock: int = 1_000) -> Card:
    rendition = Rendition(
        rendition_id="m:l", moment_id="m", lens_id=lens_id, language="en", headline="h",
        body="b", surviving_claim_ids=(), suppressed=False, suppression_reason=None,
        rendered_at=datetime.now(UTC),
    )  # fmt: skip
    return Card(rendition=rendition, display_at_clock=clock)


def test_a_card_reaches_every_session_on_its_lens():
    sessions, queues = SessionStore(), ReleaseQueues()
    a, b = sessions.create(), sessions.create()
    other = sessions.create(lens_id="team_engaged", focus_team="h")
    card = _card()
    CardRouter(sessions, queues).receive(card)
    assert queues.release_due(a, 0) == [card]
    assert queues.release_due(b, 0) == [card]
    assert queues.release_due(other, 0) == []


def test_a_released_card_is_not_released_again():
    sessions, queues = SessionStore(), ReleaseQueues()
    session = sessions.create()
    CardRouter(sessions, queues).receive(_card())
    assert len(queues.release_due(session, 0)) == 1
    assert queues.release_due(session, 0) == []


def test_a_sessions_first_release_asks_catch_up_and_the_session_clock():
    sessions, queues = SessionStore(), ReleaseQueues()
    session = sessions.create()
    with calltrace.recording() as first:
        queues.release_due(session, 0)
    with calltrace.recording() as second:
        queues.release_due(session, 0)
    assert {"Session Clock", "Catch-up", "Lens Registry"} <= set(first)
    assert "Catch-up" not in second


def test_the_registry_serves_the_default_lens_as_data():
    assert lenses.get(settings.default_lens_id) in lenses.all_lenses()
