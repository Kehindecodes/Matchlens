"""Delivery's end of the bus: each card goes to the release queue of every session on its lens.

Every card received is kept, so a session that joins late is given the cards its video has not
reached yet (D33). Without that, a viewer 45 s behind who joins at 68:00 would never see the
cards from 67:15 to 68:00, and a viewer watching from kickoff would see none.
"""

from matchlens import calltrace, control
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.session_clock import viewer_position
from matchlens.delivery.sessions import SessionStore
from matchlens.models import ViewerSession
from matchlens.rendering import Card


class CardRouter:
    def __init__(self, sessions: SessionStore, queues: ReleaseQueues):
        self._sessions = sessions
        self._queues = queues
        self._history: list[Card] = []  # every card received and not muted, in arrival order

    def receive(self, card: Card) -> None:
        calltrace.entered("Delivery")
        lens_id = card.rendition.lens_id
        if control.is_muted(lens_id, card.display_at_clock):
            return
        self._history.append(card)
        for session in self._sessions.on_lens(lens_id):
            self._queues.enqueue(card, session)

    def join(self, session: ViewerSession, match_clock_now: int) -> None:
        """Give a new session the cards on its lens that its video has not reached yet.

        What it has already passed is the catch-up summary's (D4), never a replay of cards.
        """
        calltrace.entered("Delivery")
        position = viewer_position(session, match_clock_now)
        for card in self._history:
            if card.rendition.lens_id == session.lens_id and card.display_at_clock > position:
                self._queues.enqueue(card, session)
