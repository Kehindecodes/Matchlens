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
from matchlens.delivery.sessions import LensRefused, SessionStore, UnknownSession
from matchlens.models import ClockMs, Lens, ViewerSession

WEB_DIR = Path(__file__).resolve().parents[2] / "web"


class NewSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lens_id: str | None = None
    language: str | None = None
    focus_team: str | None = None
    stream_offset_ms: ClockMs = 0  # how far this viewer's video lags the action (D7)


class LensSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lens_id: str
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
        return sessions.create(
            body.lens_id, body.language, body.focus_team, stream_offset_ms=body.stream_offset_ms
        )

    @app.get("/watch", include_in_schema=False)
    def watch() -> FileResponse:
        return FileResponse(web_dir / "watch.html")

    @app.get("/session/{session_id}")
    def get_session(session_id: str) -> ViewerSession:
        return _session(session_id)

    @app.post("/session/{session_id}/lens")
    def switch_lens(session_id: str, body: LensSwitch) -> ViewerSession:
        """Change the session's lens. The open stream carries on and uses it from the next card."""
        _session(session_id)
        try:
            return sessions.switch_lens(session_id, body.lens_id, body.focus_team)
        except LensRefused as refused:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(refused)) from None

    @app.get("/stream", response_class=EventSourceResponse)
    async def stream(
        session: Annotated[ViewerSession, Depends(_session)],
        last_event_id: Annotated[str | None, Header()] = None,
    ) -> AsyncIterator[ServerSentEvent]:
        """States as they arrive, and this session's cards as its video reaches them (D1).

        Every event's id is `<state seq>:<cards released>`, so whichever event a browser saw
        last, `Last-Event-ID` says both where the clock was and how many cards it had. A
        reconnect resumes after both; a new connection with no id starts after every card
        already released, so a rejoin replays nothing.
        """
        after_seq, sent = _resume_point(last_event_id)
        sent = queues.count_released(session.session_id) if sent is None else sent
        seq = -1 if after_seq is None else after_seq
        async for tick in hub.ticks(after_seq):
            if tick.state is not None:
                seq = tick.state.seq
                yield ServerSentEvent(data=tick.state, event="match_state", id=f"{seq}:{sent}")
            # Read afresh each tick: a lens switch replaces the session while this stream is open.
            try:
                current = sessions.get(session.session_id)
            except UnknownSession:
                return
            released = queues.release_due(current, tick.clock_ms)
            if released:
                sessions.mark_seen(current.session_id, released[-1].display_at_clock)
            for card in queues.released(current.session_id, sent):
                sent += 1
                yield ServerSentEvent(data=card, event="card", id=f"{seq}:{sent}")

    app.mount("/static", StaticFiles(directory=web_dir), name="static")
    return app


def _resume_point(last_event_id: str | None) -> tuple[int | None, int | None]:
    """The state seq and card count a `Last-Event-ID` names; None for whatever it does not."""
    if not last_event_id:
        return None, None
    seq, _, sent = last_event_id.partition(":")
    return (
        int(seq) if seq.isdigit() else None,
        int(sent) if sent.isdigit() else None,
    )
