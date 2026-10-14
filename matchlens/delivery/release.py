"""Per-session release queues. **Placeholder until D1**, which is Kehinde's.

The real queue holds each card until `display_at_clock <= match_clock_now - stream_offset_ms`
(invariant 8). Until D1 this placeholder releases everything it holds at the next call, with no
delay, as S3 and S4 allow ("send whatever arrives").
"""

from collections import defaultdict

from matchlens import calltrace, catchup, lenses
from matchlens.delivery.session_clock import viewer_position
from matchlens.models import ViewerSession
from matchlens.rendering import Card


class ReleaseQueues:
    def __init__(self) -> None:
        self._queues: dict[str, list[Card]] = defaultdict(list)
        self._joined: set[str] = set()

    def enqueue(self, card: Card, session: ViewerSession) -> None:
        """Hold `card` in this session's release queue."""
        calltrace.entered("Delivery")
        self._queues[session.session_id].append(card)

    def release_due(self, session: ViewerSession, match_clock_now: int) -> list[Card]:
        """Cards this session has now seen the action for. Placeholder: all of them."""
        calltrace.entered("Delivery")
        position = viewer_position(session, match_clock_now)
        if session.session_id not in self._joined:
            self._joined.add(session.session_id)
            self._catch_up(session, position)
        released, self._queues[session.session_id] = self._queues[session.session_id], []
        return released

    @staticmethod
    def _catch_up(session: ViewerSession, position: int) -> None:
        # Sessions are not checked against the registry until L1, so the lens may be unknown.
        try:
            lens = lenses.get(session.lens_id)
        except KeyError:
            return
        catchup.summarise(lens, 0, position)  # the summary is shown once D4 exists
