"""Tracks where each viewer is in the match"""

from matchlens import calltrace
from matchlens.models import ViewerSession


def viewer_position(session: ViewerSession, match_clock_now: int) -> int:
    """The match clock this viewer's video is showing: the action less their offset (D7).

    Both are match-clock milliseconds, never wall clock, so the rule holds at any replay speed.
    It is negative until the viewer's video reaches kickoff, and must stay so: clamped to zero, it
    would release a kickoff card to a viewer still watching the pre-match.
    """
    calltrace.entered("Session Clock")
    return match_clock_now - session.stream_offset_ms
