"""Ingest: the single writer of the raw record (D18)."""

from matchlens import calltrace
from matchlens.config.settings import settings
from matchlens.ingest.events import EventRepository, InMemoryEventRepository
from matchlens.ingest.frames import FrameAccess, FrameWindow
from matchlens.ingest.record import RecordReader
from matchlens.models import Event, Frame
from matchlens.source import MatchSetup, StreamItem


class RosterNotLoaded(RuntimeError):
    """A frame or event arrived before the roster (D16)."""


class Ingest:
    """Accepts the Match Source stream: the roster first, then frames and events in `seq` order.

    Hands out two readers. `frame_access()` is for Understanding only; `record()` is the
    agent-facing one, and cannot reach a frame.
    """

    def __init__(
        self,
        events: EventRepository | None = None,
        *,
        frame_retention_ms: int | None = None,
    ):
        self._events = InMemoryEventRepository() if events is None else events
        retention = settings.signal_window_ms if frame_retention_ms is None else frame_retention_ms
        self._window = FrameWindow(retention)
        self._setup: MatchSetup | None = None
        self._last_seq = -1
        self._team_ids: frozenset[str] = frozenset()
        self._player_ids: frozenset[str] = frozenset()

    def accept(self, item: StreamItem) -> None:
        calltrace.entered("Ingest")
        if isinstance(item, MatchSetup):
            self._load_roster(item)
            return
        if self._setup is None:
            raise RosterNotLoaded(f"{type(item).__name__} seq {item.seq} arrived before the roster")
        if item.seq <= self._last_seq:
            raise ValueError(f"seq {item.seq} arrived after seq {self._last_seq}")
        if isinstance(item, Frame):
            self._window.append(item)
        else:
            self._check_references(item)
            self._events.append(item)
        self._last_seq = item.seq

    def frame_access(self) -> FrameAccess:
        return FrameAccess(self._window)

    def record(self) -> RecordReader:
        if self._setup is None:
            raise RosterNotLoaded("there is no record before the roster")
        return RecordReader(self._setup, self._events)

    def _load_roster(self, setup: MatchSetup) -> None:
        if self._setup is not None:
            raise ValueError("the roster is loaded once, before the stream")
        self._setup = setup
        self._team_ids = frozenset(t.team_id for t in setup.match.teams)
        self._player_ids = frozenset(p.player_id for p in setup.players)

    def _check_references(self, event: Event) -> None:
        if event.team is not None and event.team not in self._team_ids:
            raise ValueError(f"event {event.event_id} names unknown team {event.team}")
        for field in ("player", "receiver", "player_on"):
            player_id = getattr(event, field)
            if player_id is not None and player_id not in self._player_ids:
                raise ValueError(f"event {event.event_id} names unknown {field} {player_id}")
