"""Fan-out of the latest `MatchState` to every open stream.

Only the latest state is kept: a viewer who reconnects is sent where the match is now, not every
tick they missed. Until the release queue (D1) exists, every session gets each state as it
arrives.
"""

import asyncio
import functools
from collections.abc import AsyncIterator

from matchlens.understanding.match_state import MatchState


class MatchStateHub:
    def __init__(self) -> None:
        self._latest: MatchState | None = None
        self._changed = asyncio.Condition()

    @property
    def latest(self) -> MatchState | None:
        return self._latest

    def _is_newer(self, seq: int) -> bool:
        return self._latest is not None and self._latest.seq > seq

    async def publish(self, state: MatchState) -> None:
        async with self._changed:
            self._latest = state
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
