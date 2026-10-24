"""The live path: `SignalReading`s as the stream arrives, not after the match (M1a).

Everything U3 and U4 built reads a finished log. `Understanding` holds what a reading needs
between calls: the epochs found so far, the last clock it has read up to, and the baselines
(`Baselines`, keyed on the epoch, so a break starts them empty). That state is in-process and
derived; the log it reads from is Ingest's.

A reading at clock `c` counts what happened up to and including `c`, so it can be taken once an
event arrives with a later clock, and not before. Clocks never go back, so by then every event
that belongs to the reading is in the log. Only events tell the time here: a frame never moves
a boundary and never reaches a value.
"""

from collections.abc import Callable, Mapping

from matchlens import calltrace
from matchlens.ingest import RecordReader
from matchlens.models import Epoch, Event, Signal, SignalPrior, SignalReading
from matchlens.source import StreamItem
from matchlens.understanding import priors as signal_priors
from matchlens.understanding.baseline import Baselines
from matchlens.understanding.epochs import detect, starts_epoch
from matchlens.understanding.signals import cadence, measure


class Understanding:
    def __init__(
        self,
        record: Callable[[], RecordReader],
        priors: Mapping[Signal, SignalPrior] | None = None,
    ):
        """`record` is Ingest's reader, so there is no way to reach a frame from here.

        With no `priors` it loads the committed ones, and a stale file raises `StalePrior`: that
        is meant to stop the process starting, not to be caught.
        """
        self._record = record
        self._baselines = Baselines(signal_priors.load() if priors is None else priors)
        self._epochs: list[Epoch] = []
        self._read_to_ms = 0  # every cadence clock up to here has been read

    def observe(self, item: StreamItem) -> list[SignalReading]:
        """The readings this item completes: those at each cadence clock it has now passed."""
        calltrace.entered("Understanding")
        if not isinstance(item, Event):
            return []
        reader = self._record()
        passed_ms = item.clock_ms - 1
        readings = [
            self._baselines.judge(measurement, epoch)
            for clock, epoch in cadence(self._epochs, passed_ms, after_ms=self._read_to_ms)
            for measurement in measure(reader, epoch, clock)
        ]
        self._read_to_ms = max(self._read_to_ms, passed_ms)
        if starts_epoch(item):
            # Found after the readings above, which belong to the epochs before it. Detecting
            # again rather than appending keeps two breaks at one clock as one epoch (U5).
            self._epochs = detect(reader)
        return readings

    @property
    def epochs(self) -> tuple[Epoch, ...]:
        """The epochs found so far, in clock order."""
        return tuple(self._epochs)

    def epoch_at(self, clock_ms: int) -> Epoch:
        """The epoch an event at `clock_ms` belongs to: one starting at `clock_ms` is the next's.

        The same convention the signal windows use, so a goal belongs to the epoch it ended.
        """
        return next(
            (e for e in reversed(self._epochs) if e.start_clock_ms < clock_ms), self._epochs[0]
        )
