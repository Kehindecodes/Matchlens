"""Fan-out of `MatchState`, and of the match clock, to every open stream.

Every state is kept, one per match second, so a stream can send each viewer the state their
video is at rather than the live one (D32): the scoreboard on the page waits by the same rule
as the cards. A viewer who reconnects is sent where their video is now, not every tick missed.

The clock is kept apart from the state because it outlives it. The last state is the final
whistle, but a viewer behind the action is still watching, so the clock keeps advancing with
`advance` after the stream ends, and a card held at full time is released when they reach it.
"""

import asyncio
import bisect
import functools
from collections.abc import AsyncIterator

from matchlens.understanding.match_state import MatchState


class MatchStateHub:
    def __init__(self) -> None:
        self._latest: MatchState | None = None
        self._history: list[MatchState] = []  # in clock order, as the stream sends them
        self._history_clocks: list[int] = []
        self._clock_ms = -1  # no match clock yet
        self._changes = 0  # counts publishes, advances and speed changes; a stream wakes for any
        self._speed: float | None = None  # the replay's, once the feed says (D3, D33)
        self._changed = asyncio.Condition()

    @property
    def latest(self) -> MatchState | None:
        return self._latest

    @property
    def clock_ms(self) -> int:
        return self._clock_ms

    @property
    def speed(self) -> float | None:
        """Match seconds per wall second, for the one match every viewer shares."""
        return self._speed

    async def set_speed(self, speed: float) -> None:
        """Ask for a new speed. The feed applies it to the replay; streams tell their pages."""
        async with self._changed:
            if speed != self._speed:
                self._speed = speed
                self._changes += 1
                self._changed.notify_all()

    def state_at(self, clock_ms: int) -> MatchState | None:
        """The last state at or before `clock_ms`, or None if the match had not reached it."""
        i = bisect.bisect_right(self._history_clocks, clock_ms)
        return self._history[i - 1] if i else None

    def _changed_since(self, changes: int) -> bool:
        return self._changes > changes

    def _is_newer(self, seq: int) -> bool:
        return self._latest is not None and self._latest.seq > seq

    async def publish(self, state: MatchState) -> None:
        async with self._changed:
            self._latest = state
            if not self._history_clocks or state.clock_ms >= self._history_clocks[-1]:
                self._history.append(state)
                self._history_clocks.append(state.clock_ms)
            self._clock_ms = max(self._clock_ms, state.clock_ms)
            self._changes += 1
            self._changed.notify_all()

    async def advance(self, clock_ms: int) -> None:
        """Move the match clock on with no new state. It never goes back."""
        async with self._changed:
            if clock_ms > self._clock_ms:
                self._clock_ms = clock_ms
                self._changes += 1
                self._changed.notify_all()

    async def follow(self, after_seq: int | None = None) -> AsyncIterator[MatchState]:
        """Each new state with a `seq` above `after_seq`, starting with the latest if it is."""
        last = -1 if after_seq is None else after_seq
        while True:
            async with self._changed:
                await self._changed.wait_for(functools.partial(self._is_newer, last))
                state = self._latest
            assert state is not None
            last = state.seq
            yield state

    async def ticks(self) -> AsyncIterator[int]:
        """The match clock, each time something changes: a state, the clock, or the speed.

        A new state can arrive on a clock the hub has already reached, so waking only when the
        clock moves would miss it.
        """
        seen = 0
        while True:
            async with self._changed:
                await self._changed.wait_for(functools.partial(self._changed_since, seen))
                seen = self._changes
                clock = self._clock_ms
            yield clock
