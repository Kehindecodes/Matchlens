"""Per-session release queues: delay only, never anticipate (invariant 8, D7).

Each session holds its own queue, ordered on `display_at_clock`, and releases from the head while

    queue.head.display_at_clock <= match_clock_now - session.stream_offset_ms

stopping at the first card that is not due. Cards can arrive out of clock order, so a scan that
released every due card wherever it sat would emit them out of order.

A released card moves to the session's log, which is what a stream sends from. A late joiner's
catch-up summary (D4) is held here from the join and goes into the log first, on the session's
first release, so it is sent once and counted like a card. A reconnecting
stream says how far into the log it got (`Last-Event-ID`) and is sent the rest, so it resumes
rather than replays. Everything here lives as long as the delivery process, like the sessions.

A mute's notice (P2) waits in the same queue at the mute's clock, so it follows the cards a viewer
is still owed. Whether it is sent is judged when it comes due: a viewer who had cards by then is
told, one who had none is not, and an unmute is told only to a viewer who was told of the pause.
"""

import heapq
import itertools
from collections import defaultdict

from matchlens import calltrace
from matchlens.catchup import CatchUp
from matchlens.control import Notice, NoticeKind
from matchlens.delivery.session_clock import viewer_position
from matchlens.models import ViewerSession
from matchlens.rendering import Card


class ReleaseQueues:
    def __init__(self) -> None:
        # (clock, arrival, entry): arrival breaks clock ties in the order entries came
        self._pending: dict[str, list[tuple[int, int, Card | Notice]]] = defaultdict(list)
        self._released: dict[str, list[Card | CatchUp | Notice]] = defaultdict(list)
        self._arrivals = itertools.count()
        self._catch_ups: dict[str, CatchUp] = {}  # held from the join to the first release
        self._told_paused: dict[str, set[str]] = defaultdict(set)  # session id -> lens ids

    def enqueue(self, card: Card, session: ViewerSession) -> None:
        """Hold `card` in this session's release queue."""
        calltrace.entered("Delivery")
        entry = (card.display_at_clock, next(self._arrivals), card)
        heapq.heappush(self._pending[session.session_id], entry)

    def enqueue_notice(self, notice: Notice, session: ViewerSession) -> None:
        """Hold `notice` in this session's queue, to come due at its clock like a card."""
        calltrace.entered("Delivery")
        entry = (notice.clock_ms, next(self._arrivals), notice)
        heapq.heappush(self._pending[session.session_id], entry)

    def hold_catch_up(self, summary: CatchUp, session: ViewerSession) -> None:
        """Hold `summary` until this session's first release, where it goes ahead of any card."""
        self._catch_ups[session.session_id] = summary

    def release_due(self, session: ViewerSession, match_clock_now: int) -> list[Card]:
        """The cards this session's video has now shown the action for, in clock order.

        Each is released once and added to the session's log. A card for a lens the session has
        since left is taken off the queue and not released: it is not this viewer's any more.
        A held catch-up goes into the log first, unless the session has left its lens too.

        A notice that comes due goes into the log between the cards, in clock order, if this
        viewer is to be told. Only the cards are returned, since they are what moves
        `last_seen_clock`.
        """
        calltrace.entered("Delivery")
        position = viewer_position(session, match_clock_now)
        summary = self._catch_ups.pop(session.session_id, None)
        if summary is not None and summary.lens_id == session.lens_id:
            self._released[session.session_id].append(summary)
        queue = self._pending[session.session_id]
        due: list[Card | Notice] = []
        had_a_card = session.last_seen_clock is not None
        while queue and queue[0][0] <= position:
            _, _, entry = heapq.heappop(queue)
            if isinstance(entry, Notice):
                if self._is_told(entry, session, had_a_card):
                    due.append(entry)
            elif entry.rendition.lens_id == session.lens_id:
                due.append(entry)
                had_a_card = True
        self._released[session.session_id].extend(due)
        return [entry for entry in due if isinstance(entry, Card)]

    def _is_told(self, notice: Notice, session: ViewerSession, had_a_card: bool) -> bool:
        """Whether this viewer is told of `notice` now (Q44: 3A).

        Only on their lens, and a pause only if they had cards: telling someone who has never
        seen one that insights are paused announces a feature by announcing its absence. An
        unmute is told only to a viewer who was told of the pause.
        """
        if notice.lens_id != session.lens_id:
            return False
        told = self._told_paused[session.session_id]
        if notice.kind is NoticeKind.PAUSED:
            if had_a_card:
                told.add(notice.lens_id)
            return had_a_card
        if notice.lens_id not in told:
            return False
        told.discard(notice.lens_id)
        return True

    def released(self, session_id: str, after: int = 0) -> list[Card | CatchUp | Notice]:
        """The session's log from the `after`-th entry on: its cards and notices, and its
        catch-up if any."""
        return self._released[session_id][after:]

    def count_released(self, session_id: str) -> int:
        return len(self._released[session_id])

    def depth(self, session_id: str) -> int:
        """How many cards this session is holding."""
        return len(self._pending[session_id])
