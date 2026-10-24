"""Delivery's end of the bus: each card goes to the release queue of every session on its lens.

Every card received is kept, so a session that joins late is given the cards its video has not
reached yet (D33). Without that, a viewer 45 s behind who joins at 68:00 would never see the
cards from 67:15 to 68:00, and a viewer watching from kickoff would see none.
"""

from matchlens import calltrace, catchup, control, lenses
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

        What it has already passed is summarised instead (D4), never replayed. Both sides are
        split at the one position, so no card is summarised and released as well. A session at
        or before kickoff has passed nothing and is given no summary.
        """
        calltrace.entered("Delivery")
        position = viewer_position(session, match_clock_now)
        passed = []
        for card in self._history:
            if card.rendition.lens_id != session.lens_id:
                continue
            if card.display_at_clock > position:
                self._queues.enqueue(card, session)
            else:
                passed.append(card)
        if position <= 0:
            return
        # Sessions are not checked against the registry until L1, so the lens may be unknown.
        try:
            lens = lenses.get(session.lens_id)
        except KeyError:
            return
        summary = catchup.summarise(lens, passed, 0, position)
        if summary is not None:
            self._queues.hold_catch_up(summary, session)
