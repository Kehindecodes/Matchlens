"""Delivery's end of the bus: each card goes to the release queue of every session on its lens."""

from matchlens import calltrace, control
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.sessions import SessionStore
from matchlens.rendering import Card


class CardRouter:
    def __init__(self, sessions: SessionStore, queues: ReleaseQueues):
        self._sessions = sessions
        self._queues = queues

    def receive(self, card: Card) -> None:
        calltrace.entered("Delivery")
        lens_id = card.rendition.lens_id
        if control.is_muted(lens_id, card.display_at_clock):
            return
        for session in self._sessions.on_lens(lens_id):
            self._queues.enqueue(card, session)
