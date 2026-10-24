"""Viewer sessions, held in process.

A session is preferences, not an account. In-process storage is enough for v1 (S3): a session
outlives a page reload, not a delivery restart.
"""

import uuid
from datetime import UTC, datetime

from matchlens import lenses
from matchlens.config.settings import settings
from matchlens.models import Scope, ViewerSession


class UnknownSession(KeyError):
    """No session has this id, for example after a delivery restart."""


class LensRefused(ValueError):
    """A switch the session cannot make: an unknown lens, or a team lens with no team."""


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

    def switch_lens(
        self, session_id: str, lens_id: str, focus_team: str | None = None
    ) -> ViewerSession:
        """Move the session to `lens_id`, replacing it with an updated copy (L5).

        This is where the session meets its lens, so the pairing is checked here: a team-scope
        lens needs `focus_team`, and any other lens clears it. A refused switch leaves the
        session as it was.
        """
        session = self.get(session_id)
        try:
            lens = lenses.get(lens_id)
        except KeyError:
            raise LensRefused(f"no lens {lens_id!r}") from None
        if lens.scope is Scope.TEAM and focus_team is None:
            raise LensRefused(f"{lens_id!r} is team scope and needs a focus_team")
        moved = session.model_copy(
            update={
                "lens_id": lens_id,
                "focus_team": focus_team if lens.scope is Scope.TEAM else None,
            }
        )
        self._sessions[session_id] = moved
        return moved

    def on_lens(self, lens_id: str) -> list[ViewerSession]:
        return [s for s in self._sessions.values() if s.lens_id == lens_id]

    def get(self, session_id: str) -> ViewerSession:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise UnknownSession(session_id) from None
