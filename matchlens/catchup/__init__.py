"""Summarises what a lens would have shown before a viewer joined"""

from matchlens import calltrace
from matchlens.models import Lens


def summarise(lens: Lens, from_clock: int, to_clock: int) -> str:
    """What `lens` showed between the two clocks. Stub: nothing to catch up on."""
    calltrace.entered("Catch-up")
    return ""
