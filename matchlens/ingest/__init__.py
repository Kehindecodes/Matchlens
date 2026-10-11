"""Holds the recent frame window in memory and enforces the frame access boundary"""

from matchlens.models import Frame
from matchlens.source import StreamItem


def accept(item: StreamItem) -> None:
    """Take one item off the Match Source stream. Stub: drops it until S2."""


def frame_window(clock_ms: int, span_ms: int) -> list[Frame]:
    """Frames in `(clock_ms - span_ms, clock_ms]`. Stub: empty until S2."""
    return []
