"""The explainer's read: the record frozen at a moment's clock (A1, invariant 6).

A `FrozenLog` is built from a moment and serves the events, readings and epochs at or before that
moment's clock, and nothing later exists from its point of view. The boundary is inclusive, so a
goal moment can cite its own goal (Q6).

The clock is the moment's and is fixed when the log is built. No read takes a clock, so no caller
can ask it for a later one, and what it holds are tuples copied at that point, so a later append
to the record, the readings or the epochs cannot reach it. It keeps no reference to the reader it
was built from, so there is nothing on it to follow to a `Frame` (invariant 1).
"""

from collections.abc import Iterable

from matchlens.ingest.record import RecordReader
from matchlens.models import Epoch, Event, Match, Moment, SignalReading


class FrozenLog:
    def __init__(
        self,
        moment: Moment,
        record: RecordReader,
        readings: Iterable[SignalReading],
        epochs: Iterable[Epoch],
    ):
        clock = moment.clock_ms
        self._clock_ms = clock
        self._match = record.match
        self._events = record.events_between(0, clock + 1)  # [from, to), so +1 includes the clock
        self._readings = tuple(r for r in readings if r.clock_ms <= clock)
        self._epochs = tuple(e for e in epochs if e.start_clock_ms <= clock)

    @property
    def clock_ms(self) -> int:
        """The clock this log is frozen at: everything in it is at or before it."""
        return self._clock_ms

    @property
    def match(self) -> Match:
        return self._match

    @property
    def events(self) -> tuple[Event, ...]:
        """Events at or before the clock, in `seq` order."""
        return self._events

    @property
    def readings(self) -> tuple[SignalReading, ...]:
        """Readings at or before the clock, in the order they were taken."""
        return self._readings

    @property
    def epochs(self) -> tuple[Epoch, ...]:
        """Epochs started at or before the clock, in clock order."""
        return self._epochs
