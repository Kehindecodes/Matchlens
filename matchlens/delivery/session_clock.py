"""Tracks where each viewer is in the match"""

from matchlens import calltrace
from matchlens.models import ViewerSession


def viewer_position(session: ViewerSession, match_clock_now: int) -> int:
    """The match clock this viewer's video is showing. Placeholder until D1: the match clock."""
    calltrace.entered("Session Clock")
    return match_clock_now
