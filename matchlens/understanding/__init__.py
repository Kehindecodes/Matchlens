"""Turns the raw stream into derived measures — possessions, shot quality, signal readings"""

from matchlens import calltrace
from matchlens.models import SignalReading
from matchlens.source import StreamItem


def observe(item: StreamItem) -> list[SignalReading]:
    """The readings this item completes. Stub: none until U3."""
    calltrace.entered("Understanding")
    return []
