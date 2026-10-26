"""The delivery HTTP surface: the page, viewer sessions, and the SSE stream.

With a `ProducerFeed` it also serves the producer view (P1, Q43: 4B) and the controls on it: mute
and unmute (P2, Q44: 4A), and the rejected-claims page and its data (P3). Without one, the page,
its stream, its files, the controls and the claims do not exist: a deployment that has not
switched it on has nothing to find, and a viewer has nothing to call.
"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Literal, override

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from starlette.responses import Response
from starlette.types import Scope

from matchlens import lenses
from matchlens.audit import Audit
from matchlens.audit.claims import ClaimsPage, claims_page
from matchlens.catchup import CatchUp
from matchlens.config.settings import settings
from matchlens.control import AlreadyMuted, Mutes, Notice, NotMuted
from matchlens.control.ladder import Ladder, LadderStatus
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.limits import Limiter, LimitsMiddleware
from matchlens.delivery.producer import ProducerFeed
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.session_clock import viewer_position
from matchlens.delivery.sessions import (
    LensRefused,
    SessionsFull,
    SessionStore,
    UnknownSession,
)
from matchlens.models import ClockMs, Lens, OverlayPacket, ProducerAction, ViewerSession
from matchlens.rendering import Card

WEB_DIR = Path(__file__).resolve().parents[2] / "web"

# The files only the producer view uses. Lower case, since the check is not case-sensitive.
PRODUCER_FILES = frozenset(
    {"producer.html", "producer.js", "producer.css", "claims.html", "claims.js", "claims.css"}
)


class _Files(StaticFiles):
    """The web directory, less the files named in `hidden`, which are then not found."""

    def __init__(self, *, directory: Path, hidden: frozenset[str]) -> None:
        super().__init__(directory=directory)
        self._hidden = hidden

    @override
    async def get_response(self, path: str, scope: Scope) -> Response:
        if path.lower() in self._hidden:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        return await super().get_response(path, scope)


class NewSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lens_id: str | None = None
    language: str | None = None
    focus_team: str | None = None
    stream_offset_ms: ClockMs = 0  # how far this viewer's video lags the action (D7)


class SpeedChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speed: float = Field(gt=0, le=settings.max_replay_speed)  # refused, never clamped (D3)


class Playback(BaseModel):
    speed: float | None  # None until the match has started
    clock_ms: int  # the live match clock; -1 before kickoff
    max_speed: float


class ModelSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: Literal["off", "on"]


_Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Intervention(BaseModel):
    """A producer muting or unmuting a lens. The reason is required; the actor is as typed,
    since there are no accounts (Q44: 4A)."""

    model_config = ConfigDict(extra="forbid")

    lens_id: str
    reason: _Text
    actor: _Text = "producer"


class LensSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lens_id: str
    focus_team: str | None = None


def create_app(
    hub: MatchStateHub,
    sessions: SessionStore,
    queues: ReleaseQueues | None = None,
    router: CardRouter | None = None,
    ladder: Ladder | None = None,
    *,
    producer: ProducerFeed | None = None,
    mutes: Mutes | None = None,
    audit: Audit | None = None,
    limits: Limiter | None = None,
    web_dir: Path = WEB_DIR,
    lifespan=None,
) -> FastAPI:
    app = FastAPI(title="MatchLens delivery", lifespan=lifespan)
    if limits is not None:  # X4: the deployed app is limited; a test's app is not unless it asks
        app.add_middleware(LimitsMiddleware, limiter=limits)
    queues = ReleaseQueues() if queues is None else queues
    mutes = Mutes() if mutes is None else mutes
    audit = Audit() if audit is None else audit
    router = CardRouter(sessions, queues, mutes) if router is None else router
    ladder = Ladder() if ladder is None else ladder

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
        try:
            session = sessions.create(
                body.lens_id, body.language, body.focus_team, stream_offset_ms=body.stream_offset_ms
            )
        except SessionsFull:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "the demo is full: try again shortly",
                headers={"Retry-After": "60"},
            ) from None
        router.join(session, hub.clock_ms)
        return session

    @app.get("/watch", include_in_schema=False)
    def watch() -> FileResponse:
        return FileResponse(web_dir / "watch.html")

    @app.get("/playback")
    def get_playback() -> Playback:
        """How fast the match is running and where it is, live (D3)."""
        return Playback(speed=hub.speed, clock_ms=hub.clock_ms, max_speed=settings.max_replay_speed)

    @app.post("/playback")
    async def set_playback(body: SpeedChange) -> Playback:
        """Change the speed of the one match every viewer shares (D33)."""
        await hub.set_speed(body.speed)
        return get_playback()

    @app.get("/ladder")
    def get_ladder() -> LadderStatus:
        """Which rung the match is on, and whether each model is up (A5)."""
        return ladder.status()

    @app.post("/ladder")
    def set_ladder(body: ModelSwitch) -> LadderStatus:
        """Switch the models off or on, as if unreachable: the demo's kill (Q41: 4A).

        The ladder sees an ordinary failure and drops a rung; on again, it climbs by its rule.
        """
        ladder.switch(body.models == "on")
        return ladder.status()

    @app.get("/delay", include_in_schema=False)
    def delay() -> FileResponse:
        """Two viewers on different offsets, side by side (D2)."""
        return FileResponse(web_dir / "delay.html")

    @app.get("/session/{session_id}")
    def get_session(session_id: str) -> ViewerSession:
        return _session(session_id)

    @app.get("/session/{session_id}/overlays")
    def overlays(session_id: str, after: Annotated[int, Query(ge=0)] = 0) -> list[OverlayPacket]:
        """The overlay packets this session has had released, from the `after`-th on (D5).

        One per card, in the order the cards were released, which is `display_at_clock` order.
        Only what the viewer's video has reached: a player polling this is never handed an
        overlay for something it has not shown yet (invariant 8). The stream's `card` events
        carry the same packet, for a player that would rather listen than poll.
        """
        _session(session_id)
        cards = [e for e in queues.released(session_id) if isinstance(e, Card)]
        return [card.overlay for card in cards[after:]]

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
        """The state and the cards this session's video has reached, as it reaches them (D1, D32).

        A late joiner's catch-up (D4) comes first, as a `catch_up` event counted like a card.

        Every event's id is `<state seq>:<cards released>`, so whichever event a browser saw
        last, `Last-Event-ID` says both where the clock was and how many cards it had. A
        reconnect resumes after both; a new connection with no id starts after every card
        already released, so a rejoin replays nothing.
        """
        after_seq, sent = _resume_point(last_event_id)
        sent = queues.count_released(session.session_id) if sent is None else sent
        seq = -1 if after_seq is None else after_seq
        speed = None
        rung_version = ladder.version  # the page reads `/ladder` on load; this sends changes
        async for clock_ms in hub.ticks():
            if hub.speed != speed:  # the speed is live, not delayed: it is how the match runs
                speed = hub.speed
                yield ServerSentEvent(data={"speed": speed}, event="playback")
            if ladder.version != rung_version:  # live too: a system status, not a card (Q41)
                rung_version = ladder.version
                yield ServerSentEvent(data=ladder.status(), event="ladder")
            # Read afresh each tick: a lens switch replaces the session while this stream is open.
            try:
                current = sessions.get(session.session_id)
            except UnknownSession:
                return
            # The state this viewer's video is at, not the live one: the page's scoreboard stands
            # in for the platform's, which is in the video and as late as it is (D32).
            due = hub.state_at(viewer_position(current, clock_ms))
            if due is not None and due.seq > seq:
                seq = due.seq
                yield ServerSentEvent(data=due, event="match_state", id=f"{seq}:{sent}")
            released = queues.release_due(current, clock_ms)
            if released:
                sessions.mark_seen(current.session_id, released[-1].display_at_clock)
            for entry in queues.released(current.session_id, sent):
                sent += 1
                event = _event_name(entry)
                yield ServerSentEvent(data=entry, event=event, id=f"{seq}:{sent}")

    if producer is not None:

        @app.get("/producer", include_in_schema=False)
        def producer_page() -> FileResponse:
            """Every lens on one screen, with what a viewer is never shown (P1)."""
            return FileResponse(web_dir / "producer.html")

        @app.get("/producer/stream", response_class=EventSourceResponse)
        async def producer_stream() -> AsyncIterator[ServerSentEvent]:
            """What each lens last did and why, sent whole each time one of them changes.

            Live, not held to a viewer's clock: this is the producer's, not a viewer's, and it
            carries no card. A reconnect is sent the current state, so there is no id to resume.
            """
            async for snapshot in producer.follow():
                yield ServerSentEvent(data=snapshot, event="lenses")

        async def intervene(body: Intervention, mute: bool) -> ProducerAction:
            """Mute or unmute a lens at the live match clock, log it, and tell its viewers.

            The match clock is not touched: a mute is a fact about later cards, not a pause.
            """
            try:
                lenses.get(body.lens_id)
            except KeyError:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown lens") from None
            act = mutes.mute if mute else mutes.unmute
            try:
                action = act(body.lens_id, max(0, hub.clock_ms), body.actor, body.reason)
            except (AlreadyMuted, NotMuted) as refused:
                said = "already muted" if isinstance(refused, AlreadyMuted) else "not muted"
                raise HTTPException(status.HTTP_409_CONFLICT, f"{body.lens_id} is {said}") from None
            router.notify(Notice.of(action))
            producer.changed()
            return action

        @app.post("/producer/mute", status_code=status.HTTP_201_CREATED)
        async def mute_lens(body: Intervention) -> ProducerAction:
            """Stop a lens's cards from now on (P2). Cards already queued still release."""
            return await intervene(body, mute=True)

        @app.post("/producer/unmute", status_code=status.HTTP_201_CREATED)
        async def unmute_lens(body: Intervention) -> ProducerAction:
            """Let a lens's cards through again from now on. What was stopped is not back-filled."""
            return await intervene(body, mute=False)

        @app.get("/producer/actions")
        def producer_actions() -> list[ProducerAction]:
            """Every mute and unmute, in the order they were made."""
            return mutes.actions()

        @app.get("/producer/claims", include_in_schema=False)
        def claims_html() -> FileResponse:
            """Every claim of the match with its verdict and its six checks (P3)."""
            return FileResponse(web_dir / "claims.html")

        @app.get("/producer/claims/data")
        def claims_data(after: Annotated[int, Query(ge=0)] = 0) -> ClaimsPage:
            """The claims of the moments Audit recorded after the `after`-th, and the totals.

            Read from the trail as it is: nothing is checked or recomputed here. Live, like the
            producer's stream, and never reachable from a viewer's page.
            """
            return claims_page(audit, after)

    hidden = frozenset() if producer is not None else PRODUCER_FILES
    app.mount("/static", _Files(directory=web_dir, hidden=hidden), name="static")
    return app


def _event_name(entry: Card | CatchUp | Notice) -> str:
    match entry:
        case CatchUp():
            return "catch_up"
        case Notice():
            return "notice"
        case Card():
            return "card"


def _resume_point(last_event_id: str | None) -> tuple[int | None, int | None]:
    """The state seq and card count a `Last-Event-ID` names; None for whatever it does not."""
    if not last_event_id:
        return None, None
    seq, _, sent = last_event_id.partition(":")
    return (
        int(seq) if seq.isdigit() else None,
        int(sent) if sent.isdigit() else None,
    )
