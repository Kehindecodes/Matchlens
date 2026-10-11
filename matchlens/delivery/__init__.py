"""Releases each rendition to a session when that session's clock reaches it"""

from matchlens.models import Rendition, ViewerSession


def enqueue(rendition: Rendition, session: ViewerSession) -> None:
    """Hold `rendition` in this session's release queue. Stub: D1 implements it."""
    raise NotImplementedError("the release queue lands in D1")


def release_due(session: ViewerSession, match_clock_now: int) -> list[Rendition]:
    """Renditions this session has now seen the action for. Stub: D1 implements it."""
    raise NotImplementedError("the release queue lands in D1")
