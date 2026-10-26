"""Delivery's end of the bus: each card goes to the release queue of every session on its lens.

Every card received is kept, so a session that joins late is given the cards its video has not
reached yet (D33). Without that, a viewer 45 s behind who joins at 68:00 would never see the
cards from 67:15 to 68:00, and a viewer watching from kickoff would see none.

A mute (P2) stops the cards that arrive after it and leaves every queue as it is, and the viewers
it concerns are told through their own queues, so a notice never overtakes a card they are owed.
"""

import logging

from matchlens import calltrace, catchup, lenses
from matchlens.control import Mutes, Notice
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.session_clock import viewer_position
from matchlens.delivery.sessions import SessionStore
from matchlens.models import ViewerSession
from matchlens.rendering import Card

logger = logging.getLogger(__name__)


class CardRouter:
    def __init__(
        self, sessions: SessionStore, queues: ReleaseQueues, mutes: Mutes | None = None
    ) -> None:
        self._sessions = sessions
        self._queues = queues
        self._mutes = Mutes() if mutes is None else mutes
        self._history: list[Card] = []  # every card received and not muted, in arrival order
        self._notices: list[Notice] = []  # every mute and unmute, for a viewer who joins late

    def receive(self, card: Card) -> None:
        calltrace.entered("Delivery")
        lens_id = card.rendition.lens_id
        if self._mutes.stops(lens_id, card.display_at_clock):
            # The pipeline records a muted lens's silence as a `muted` rendition. A card that was
            # already past Selection when the click landed has no such record, so say so here.
            logger.info("router: %s stopped, %s is muted", card.rendition.rendition_id, lens_id)
            return
        self._history.append(card)
        for session in self._sessions.on_lens(lens_id):
            self._queues.enqueue(card, session)

    def notify(self, notice: Notice) -> None:
        """Tell the sessions on the notice's lens, each when their own video reaches its clock.

        Held in every queue now and judged when released: a viewer is told only if they had cards
        by then. Kept for a viewer who joins before that clock.
        """
        calltrace.entered("Delivery")
        self._notices.append(notice)
        for session in self._sessions.on_lens(notice.lens_id):
            self._queues.enqueue_notice(notice, session)

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
        for notice in self._notices:
            if notice.lens_id == session.lens_id and notice.clock_ms > position:
                self._queues.enqueue_notice(notice, session)
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
