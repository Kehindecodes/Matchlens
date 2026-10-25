"""What a claim is checked against: the record as it stood when the check ran.

Not the explainer's frozen log. A claim that cites an event after its moment's clock must still
be able to *resolve* that event, so that `temporal` fails it for the right reason rather than
`citation` failing it for the wrong one. A snapshot rather than a view, so a check on the
model's thread (Q34: A) reads what was there when the moment was handed over, however far the
match has moved on. There is no frame on it (invariant 1).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property

from matchlens.ingest import RecordReader
from matchlens.models import Event, Match, Player, SignalReading

_WHOLE_LOG_MS = 2**62  # past any match clock


@dataclass(frozen=True)
class Record:
    match: Match
    players: tuple[Player, ...]
    events: tuple[Event, ...]
    readings: tuple[SignalReading, ...]

    @classmethod
    def of(cls, reader: RecordReader, readings: Iterable[SignalReading]) -> "Record":
        return cls(
            reader.match, reader.players, reader.events_between(0, _WHOLE_LOG_MS), tuple(readings)
        )

    @cached_property
    def event(self) -> dict[str, Event]:
        return {e.event_id: e for e in self.events}

    @cached_property
    def reading(self) -> dict[str, SignalReading]:
        return {r.reading_id: r for r in self.readings}

    @cached_property
    def player(self) -> dict[str, Player]:
        return {p.player_id: p for p in self.players}

    def until(self, clock_ms: int) -> tuple[Event, ...]:
        """The events at or before `clock_ms`, in `seq` order."""
        return tuple(e for e in self.events if e.clock_ms <= clock_ms)
