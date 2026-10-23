"""The delivery HTTP surface: the page, viewer sessions, and the SSE stream."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from matchlens import lenses
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.sessions import SessionStore, UnknownSession
from matchlens.models import Lens, ViewerSession

WEB_DIR = Path(__file__).resolve().parents[2] / "web"


class NewSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lens_id: str | None = None
    language: str | None = None
    focus_team: str | None = None


def create_app(
    hub: MatchStateHub,
    sessions: SessionStore,
    queues: ReleaseQueues | None = None,
    *,
    web_dir: Path = WEB_DIR,
    lifespan=None,
) -> FastAPI:
    app = FastAPI(title="MatchLens delivery", lifespan=lifespan)
    queues = ReleaseQueues() if queues is None else queues

    def _session(session_id: str) -> ViewerSession:
        try:
            return sessions.get(session_id)
        except UnknownSession:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown session") from None

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(web_dir / "index.html")

    @app.get("/lenses")
    def list_lenses() -> list[Lens]:
        """Every active lens, so the page learns them as data (invariant 10)."""
        return lenses.all_lenses()

    @app.post("/session", status_code=status.HTTP_201_CREATED)
    def create_session(body: NewSession | None = None) -> ViewerSession:
        body = body or NewSession()
        return sessions.create(body.lens_id, body.language, body.focus_team)

    @app.get("/session/{session_id}")
    def get_session(session_id: str) -> ViewerSession:
        return _session(session_id)

    @app.get("/stream", response_class=EventSourceResponse)
    async def stream(
        session: Annotated[ViewerSession, Depends(_session)],
        last_event_id: Annotated[str | None, Header()] = None,
    ) -> AsyncIterator[ServerSentEvent]:
        after = int(last_event_id) if last_event_id and last_event_id.isdigit() else None
        async for state in hub.follow(after):
            yield ServerSentEvent(data=state, event="match_state", id=str(state.seq))
            # Cards carry no id: Last-Event-ID tracks the clock, and a released card is gone.
            for card in queues.release_due(session, state.clock_ms):
                yield ServerSentEvent(data=card, event="card")

    app.mount("/static", StaticFiles(directory=web_dir), name="static")
    return app
