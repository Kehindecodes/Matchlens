"""The agent-facing read of the raw record: the roster and the event log, never frames.

This is what Explanation and Verification are given. It holds no reference to the frame window,
directly or through Ingest, so there is nothing on it to follow to a `Frame` (invariant 1).
"""

from matchlens.ingest.events import EventRepository
from matchlens.models import Event, Match, Player
from matchlens.source import MatchSetup


class RecordReader:
    def __init__(self, setup: MatchSetup, events: EventRepository):
        self._setup = setup
        self._events = events

    @property
    def match(self) -> Match:
        return self._setup.match

    @property
    def players(self) -> tuple[Player, ...]:
        return self._setup.players

    def events_between(self, from_clock_ms: int, to_clock_ms: int) -> tuple[Event, ...]:
        """Events with `from_clock_ms <= clock_ms < to_clock_ms`, in `seq` order."""
        return self._events.between(from_clock_ms, to_clock_ms)
