"""Viewer sessions, held in process.

A session is preferences, not an account. In-process storage is enough for v1 (S3): a session
outlives a page reload, not a delivery restart.
"""

import uuid
from datetime import UTC, datetime

from matchlens.config.settings import settings
from matchlens.models import ViewerSession


class UnknownSession(KeyError):
    """No session has this id, for example after a delivery restart."""


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ViewerSession] = {}

    def create(
        self,
        lens_id: str | None = None,
        language: str | None = None,
        focus_team: str | None = None,
    ) -> ViewerSession:
        """A new session. With no lens it gets the default, whole match at casual depth (V1)."""
        session = ViewerSession(
            session_id=uuid.uuid4().hex,
            lens_id=settings.default_lens_id if lens_id is None else lens_id,
            language=settings.default_language if language is None else language,
            joined_at=datetime.now(UTC),
            focus_team=focus_team,
            focus_player=None,
            last_seen_clock=None,
            stream_offset_ms=0,  # set by D1
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> ViewerSession:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise UnknownSession(session_id) from None
