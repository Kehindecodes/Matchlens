from datetime import UTC, datetime

from matchlens import calltrace, lenses
from matchlens.config import settings
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.models import MomentType, Rendition
from matchlens.rendering import Card
from tests.overlays import overlay_for


def _card(lens_id: str = "match_casual", clock: int = 1_000) -> Card:
    rendition = Rendition(
        rendition_id="m:l", moment_id="m", lens_id=lens_id, language="en", headline="h",
        body="b", surviving_claim_ids=(), suppressed=False, suppression_reason=None,
        rendered_at=datetime.now(UTC),
    )  # fmt: skip
    return Card(
        rendition=rendition,
        display_at_clock=clock,
        moment_type=MomentType.CHANCE,
        importance=0.5,
        body_in_full="b",
        overlay=overlay_for(rendition, clock),
    )


def test_a_card_reaches_every_session_on_its_lens():
    sessions, queues = SessionStore(), ReleaseQueues()
    a, b = sessions.create(), sessions.create()
    other = sessions.create(lens_id="team_engaged", focus_team="h")
    card = _card()
    CardRouter(sessions, queues).receive(card)
    assert queues.release_due(a, card.display_at_clock) == [card]
    assert queues.release_due(b, card.display_at_clock) == [card]
    assert queues.release_due(other, card.display_at_clock) == []


def test_a_released_card_is_not_released_again():
    sessions, queues = SessionStore(), ReleaseQueues()
    session = sessions.create()
    CardRouter(sessions, queues).receive(_card())
    assert len(queues.release_due(session, 1_000)) == 1
    assert queues.release_due(session, 1_000) == []


def test_a_late_join_asks_catch_up_and_the_lens_registry_and_a_release_does_not():
    sessions, queues = SessionStore(), ReleaseQueues()
    router = CardRouter(sessions, queues)
    router.receive(_card())
    session = sessions.create()
    with calltrace.recording() as join:
        router.join(session, 2_000)
    with calltrace.recording() as release:
        queues.release_due(session, 2_000)
    assert {"Session Clock", "Catch-up", "Lens Registry"} <= set(join)
    assert "Catch-up" not in release


def test_the_registry_serves_the_default_lens_as_data():
    assert lenses.get(settings.default_lens_id) in lenses.all_lenses()
