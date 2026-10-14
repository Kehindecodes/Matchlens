"""Decides which measured changes are worth saying something about"""

from collections.abc import Sequence

from matchlens import calltrace
from matchlens.models import Event, Frame, Moment, MomentType, Ref, RefKind, SignalReading

# S4's hardcoded moment fires at 67:12 of match clock, the prototype's reference moment.
SKELETON_CLOCK_MS = 67 * 60_000 + 12_000


class Spotter:
    """Stub until M1: fires one hardcoded moment, on the first team event at or after 67:12.

    It cites that event, so even the stub moment points at its input (invariant 4).
    """

    def __init__(self) -> None:
        self._fired = False

    def consider(self, readings: Sequence[SignalReading], item: Frame | Event) -> Moment | None:
        """The moment these readings fire at `item`, if any."""
        calltrace.entered("Spotting")
        if self._fired or not isinstance(item, Event) or item.team is None:
            return None
        if item.clock_ms < SKELETON_CLOCK_MS:
            return None
        self._fired = True
        return Moment(
            moment_id=f"moment-{item.event_id}",
            clock_ms=item.clock_ms,
            type=MomentType.PATTERN,
            subject=Ref(kind=RefKind.TEAM, id=item.team),
            importance=1.0,
            trigger_reading_ids=(),
            trigger_event_ids=(item.event_id,),
            epoch_id="epoch-unknown",  # epochs land in U5
            model="hardcoded",
            model_version="S4",
        )
