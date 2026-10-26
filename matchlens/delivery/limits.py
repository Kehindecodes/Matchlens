"""Per-client limits on the public endpoints, for the judging window (X4).

One replica, a public URL and an open-ended stream is a resource anyone can use up by accident.
Every request falls in one bucket, and each bucket has its own budget per client:

- a new session: each one stays in memory until the container restarts
- any other change: the speed, the model switch, a lens, a mute reach every viewer
- a read: pages, files, state
- an open stream: each is woken on every tick of the match, so it costs the most

The window is the last minute, sliding. A refused request is not counted, so a client that keeps
knocking is let in again a minute after it stops, not a minute after its last knock.

Plain ASGI, not `BaseHTTPMiddleware`: that wraps every response in a task of its own and is
unsafe with streams that outlive the request.
"""

import json
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto

from starlette.types import ASGIApp, Receive, Scope, Send

from matchlens.config.settings import settings

WINDOW_S = 60.0
_STREAM_PATHS = frozenset({"/stream", "/producer/stream"})
_RETRY_WHEN_FULL_S = 5.0  # a stream slot frees when someone closes a tab: soon, not on a schedule


class Bucket(Enum):
    NEW_SESSION = auto()
    CHANGE = auto()
    READ = auto()
    STREAM = auto()


def bucket_of(method: str, path: str) -> Bucket:
    if path in _STREAM_PATHS:
        return Bucket.STREAM
    if method == "POST" and path == "/session":
        return Bucket.NEW_SESSION
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return Bucket.CHANGE
    return Bucket.READ


@dataclass(frozen=True)
class Refusal:
    status: int
    retry_after_s: float
    detail: str


class _Window:
    """How many requests each client has made in the last minute."""

    def __init__(self, allowed: int, clock: Callable[[], float]) -> None:
        self._allowed = allowed
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._swept_at = clock()

    @property
    def clients(self) -> set[str]:
        return set(self._hits)

    def hit(self, client: str) -> float | None:
        """Count a request, or return the seconds until the client has room for it."""
        now = self._clock()
        self._sweep(now)
        hits = self._hits[client]
        while hits and hits[0] <= now - WINDOW_S:
            hits.popleft()
        if len(hits) >= self._allowed:
            return hits[0] + WINDOW_S - now
        hits.append(now)
        return None

    def _sweep(self, now: float) -> None:
        """Forget clients with nothing in the window, once a minute, so a client is not held
        in memory for as long as the container lives."""
        if now - self._swept_at < WINDOW_S:
            return
        self._swept_at = now
        for client in [
            c for c, hits in self._hits.items() if not hits or hits[-1] <= now - WINDOW_S
        ]:
            del self._hits[client]


class Limiter:
    """The budgets, and who has spent what. One per process; the app holds the only one."""

    def __init__(
        self,
        *,
        new_sessions_per_min: int,
        changes_per_min: int,
        reads_per_min: int,
        streams_per_client: int,
        streams_total: int,
        trust_forwarded_for: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._windows = {
            Bucket.NEW_SESSION: _Window(new_sessions_per_min, clock),
            Bucket.CHANGE: _Window(changes_per_min, clock),
            Bucket.READ: _Window(reads_per_min, clock),
        }
        self._streams_per_client = streams_per_client
        self._streams_total = streams_total
        self._streams: dict[str, int] = {}
        self._trust_forwarded_for = trust_forwarded_for

    @classmethod
    def from_settings(cls) -> "Limiter":
        return cls(
            new_sessions_per_min=settings.limit_new_sessions_per_min,
            changes_per_min=settings.limit_changes_per_min,
            reads_per_min=settings.limit_reads_per_min,
            streams_per_client=settings.limit_streams_per_client,
            streams_total=settings.limit_streams_total,
            trust_forwarded_for=settings.trust_forwarded_for,
        )

    @property
    def tracked_clients(self) -> int:
        return len(set().union(*(window.clients for window in self._windows.values())))

    def client_of(self, scope: Scope) -> str:
        """Who is asking.

        Behind the Container Apps ingress every request reaches the app from the ingress, so the
        peer address is the same for every visitor and one visitor's limit would be everyone's.
        The ingress appends the address it saw to `X-Forwarded-For` and provides nothing else:
        whatever is left of that is the client's own writing. So the rightmost entry is the
        client, and it is read only where something trusted sits in front of the app.
        """
        if self._trust_forwarded_for:
            forwarded = [v for name, v in scope["headers"] if name == b"x-forwarded-for"]
            if forwarded:
                rightmost = forwarded[-1].decode("latin-1").rsplit(",", 1)[-1].strip()
                if rightmost:
                    return rightmost
        peer = scope.get("client")
        return peer[0] if peer else "unknown"

    def admit(self, bucket: Bucket, client: str) -> Refusal | None:
        """Take what this request costs, or say why not. A stream must be `close_stream`ed."""
        if bucket is Bucket.STREAM:
            return self._open_stream(client)
        wait = self._windows[bucket].hit(client)
        if wait is None:
            return None
        return Refusal(429, wait, f"too many requests: slow down and retry in {wait:.0f} s")

    def _open_stream(self, client: str) -> Refusal | None:
        # Opening is counted as a read too, so opening and closing in a loop is not free.
        wait = self._windows[Bucket.READ].hit(client)
        if wait is not None:
            return Refusal(429, wait, f"too many requests: slow down and retry in {wait:.0f} s")
        if self._streams.get(client, 0) >= self._streams_per_client:
            return Refusal(429, _RETRY_WHEN_FULL_S, "too many open streams from this address")
        if sum(self._streams.values()) >= self._streams_total:
            return Refusal(503, _RETRY_WHEN_FULL_S, "the demo is full: try again shortly")
        self._streams[client] = self._streams.get(client, 0) + 1
        return None

    def close_stream(self, client: str) -> None:
        remaining = self._streams.get(client, 0) - 1
        if remaining > 0:
            self._streams[client] = remaining
        else:
            self._streams.pop(client, None)


class LimitsMiddleware:
    def __init__(self, app: ASGIApp, limiter: Limiter) -> None:
        self.app = app
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # the lifespan, and anything that is not a request
            await self.app(scope, receive, send)
            return
        client = self.limiter.client_of(scope)
        bucket = bucket_of(scope["method"], scope["path"])
        refusal = self.limiter.admit(bucket, client)
        if refusal is not None:
            await _refuse(send, refusal)
            return
        if bucket is not Bucket.STREAM:
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:  # a closed tab ends the call by return or by cancellation; both give the slot back
            self.limiter.close_stream(client)


async def _refuse(send: Send, refusal: Refusal) -> None:
    body = json.dumps({"detail": refusal.detail}).encode()
    retry_after = max(1, round(refusal.retry_after_s + 0.5))
    await send(
        {
            "type": "http.response.start",
            "status": refusal.status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"retry-after", str(retry_after).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
