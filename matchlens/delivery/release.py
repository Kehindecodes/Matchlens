"""Per-session release queues: delay only, never anticipate (invariant 8, D7).

Each session holds its own queue, ordered on `display_at_clock`, and releases from the head while

    queue.head.display_at_clock <= match_clock_now - session.stream_offset_ms

stopping at the first card that is not due. Cards can arrive out of clock order, so a scan that
released every due card wherever it sat would emit them out of order.

A released card moves to the session's log, which is what a stream sends from. A reconnecting
stream says how far into the log it got (`Last-Event-ID`) and is sent the rest, so it resumes
rather than replays. Everything here lives as long as the delivery process, like the sessions.
"""

import heapq
import itertools
from collections import defaultdict

from matchlens import calltrace, catchup, lenses
from matchlens.delivery.session_clock import viewer_position
from matchlens.models import ViewerSession
from matchlens.rendering import Card


class ReleaseQueues:
    def __init__(self) -> None:
        # (display_at_clock, arrival, card): arrival breaks clock ties in the order cards came
        self._pending: dict[str, list[tuple[int, int, Card]]] = defaultdict(list)
        self._released: dict[str, list[Card]] = defaultdict(list)
        self._arrivals = itertools.count()
        self._joined: set[str] = set()

    def enqueue(self, card: Card, session: ViewerSession) -> None:
        """Hold `card` in this session's release queue."""
        calltrace.entered("Delivery")
        entry = (card.display_at_clock, next(self._arrivals), card)
        heapq.heappush(self._pending[session.session_id], entry)

    def release_due(self, session: ViewerSession, match_clock_now: int) -> list[Card]:
        """The cards this session's video has now shown the action for, in clock order.

        Each is released once and added to the session's log. A card for a lens the session has
        since left is taken off the queue and not released: it is not this viewer's any more.
        """
        calltrace.entered("Delivery")
        position = viewer_position(session, match_clock_now)
        if session.session_id not in self._joined:
            self._joined.add(session.session_id)
            self._catch_up(session, position)
        queue = self._pending[session.session_id]
        released = []
        while queue and queue[0][0] <= position:
            _, _, card = heapq.heappop(queue)
            if card.rendition.lens_id == session.lens_id:
                released.append(card)
        self._released[session.session_id].extend(released)
        return released

    def released(self, session_id: str, after: int = 0) -> list[Card]:
        """The cards this session has had released, from the `after`-th on."""
        return self._released[session_id][after:]

    def count_released(self, session_id: str) -> int:
        return len(self._released[session_id])

    def depth(self, session_id: str) -> int:
        """How many cards this session is holding."""
        return len(self._pending[session_id])

    @staticmethod
    def _catch_up(session: ViewerSession, position: int) -> None:
        # Sessions are not checked against the registry until L1, so the lens may be unknown.
        try:
            lens = lenses.get(session.lens_id)
        except KeyError:
            return
        catchup.summarise(lens, 0, max(0, position))  # the summary is shown once D4 exists
