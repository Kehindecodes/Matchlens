"""Tracks where each viewer is in the match"""

from matchlens.models import ViewerSession


def viewer_position(session: ViewerSession, match_clock_now: int) -> int:
    """The match clock this viewer's video is showing. Stub: D1 implements it."""
    raise NotImplementedError("the session clock lands in D1")
