"""Event persistence behind a repository interface.

The database is Postgres (D19), and its implementation lands in S5 behind this same interface.
Until then events live in memory. The log is append-only (invariant 2): no update, no delete.
"""

import bisect
from typing import Protocol

from matchlens.models import Event


class EventRepository(Protocol):
    def append(self, event: Event) -> None:
        """Store one event. Events arrive in `seq` order; an `event_id` is stored once."""
        ...

    def between(self, from_clock_ms: int, to_clock_ms: int) -> tuple[Event, ...]:
        """Events with `from_clock_ms <= clock_ms < to_clock_ms`, in `seq` order."""
        ...


class InMemoryEventRepository:
    def __init__(self) -> None:
        self._events: list[Event] = []
        self._clocks: list[int] = []
        self._ids: set[str] = set()

    def __len__(self) -> int:
        return len(self._events)

    def append(self, event: Event) -> None:
        if event.event_id in self._ids:
            raise ValueError(f"event {event.event_id} is already stored; the log is append-only")
        if self._events and event.seq <= self._events[-1].seq:
            raise ValueError("events must arrive in seq order")
        if self._clocks and event.clock_ms < self._clocks[-1]:
            raise ValueError("events must arrive in clock order")
        self._events.append(event)
        self._clocks.append(event.clock_ms)
        self._ids.add(event.event_id)

    def between(self, from_clock_ms: int, to_clock_ms: int) -> tuple[Event, ...]:
        lo = bisect.bisect_left(self._clocks, from_clock_ms)
        hi = bisect.bisect_left(self._clocks, to_clock_ms)
        return tuple(self._events[lo:hi])
