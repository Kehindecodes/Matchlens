"""Fan-out of the latest `MatchState`, and of the match clock, to every open stream.

Only the latest state is kept: a viewer who reconnects is sent where the match is now, not every
tick they missed. Every session gets each state as it arrives; cards wait in the release queue.

The clock is kept apart from the state because it outlives it. The last state is the final
whistle, but a viewer behind the action is still watching, so the clock keeps advancing with
`advance` after the stream ends, and a card held at full time is released when they reach it.
"""

import asyncio
import functools
from collections.abc import AsyncIterator
from dataclasses import dataclass

from matchlens.understanding.match_state import MatchState


@dataclass(frozen=True)
class Tick:
    """What a stream wakes for: a newer state, if there is one, and the match clock now."""

    state: MatchState | None
    clock_ms: int


class MatchStateHub:
    def __init__(self) -> None:
        self._latest: MatchState | None = None
        self._clock_ms = -1  # no match clock yet
        self._changed = asyncio.Condition()

    @property
    def latest(self) -> MatchState | None:
        return self._latest

    @property
    def clock_ms(self) -> int:
        return self._clock_ms

    def _is_newer(self, seq: int) -> bool:
        return self._latest is not None and self._latest.seq > seq

    async def publish(self, state: MatchState) -> None:
        async with self._changed:
            self._latest = state
            self._clock_ms = max(self._clock_ms, state.clock_ms)
            self._changed.notify_all()

    async def advance(self, clock_ms: int) -> None:
        """Move the match clock on with no new state. It never goes back."""
        async with self._changed:
            if clock_ms > self._clock_ms:
                self._clock_ms = clock_ms
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

    async def ticks(self, after_seq: int | None = None) -> AsyncIterator[Tick]:
        """A tick whenever a state above `after_seq` arrives or the clock moves on."""
        last_seq = -1 if after_seq is None else after_seq
        last_clock = -1

        def woken() -> bool:
            return self._is_newer(last_seq) or self._clock_ms > last_clock

        while True:
            async with self._changed:
                await self._changed.wait_for(woken)
                newer = self._latest if self._is_newer(last_seq) else None
                clock = self._clock_ms
            if newer is not None:
                last_seq = newer.seq
            last_clock = clock
            yield Tick(state=newer, clock_ms=clock)
