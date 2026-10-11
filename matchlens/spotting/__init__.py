"""Decides which measured changes are worth saying something about"""

from collections.abc import Sequence

from matchlens.models import Moment, SignalReading


def consider(readings: Sequence[SignalReading]) -> Moment | None:
    """The moment these readings fire, if any. Stub: never fires until M1."""
    return None
