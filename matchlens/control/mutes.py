"""The mute circuit breaker: which lenses are stopped, from when, and who stopped them (P2).

A mute covers a stretch of the match clock, from the clock it was made at to the clock of its
unmute. It stops the cards that come after it and nothing already in a release queue, so it never
delays a card and never retracts one (invariant 8). An unmute does not bring back what was
stopped: a card whose moment is inside a mute stays gone, however late it arrives.

A card is published after its moment, so a click can land between the two (Q44: 2B). A card is
therefore stopped if its moment is inside a mute, or if the lens is muted when the card arrives.

Every mute and unmute is a `ProducerAction` (`suppress` and `release` on a lens), kept in the
order they were made. In-process, like the sessions: it lives as long as the delivery app.
"""

import itertools
import threading
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from matchlens import calltrace
from matchlens.models import ClockMs, ProducerAction, ProducerActionType, Ref, RefKind


class AlreadyMuted(ValueError):
    """The lens is already muted, and a second mute would log an intervention that did nothing."""


class NotMuted(ValueError):
    """The lens is not muted, so there is nothing to undo."""


class NoticeKind(StrEnum):
    PAUSED = "paused"
    RESUMED = "resumed"


class Notice(BaseModel):
    """What a viewer who had cards is told when their lens is muted or unmuted (Q44: 3A).

    A stream message, like `Card`: sent, never stored. It is held in each session's release queue
    at `clock_ms`, so it reaches a viewer when their video does and not before.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    lens_id: str
    kind: NoticeKind
    clock_ms: ClockMs

    @classmethod
    def of(cls, action: ProducerAction) -> "Notice":
        """The notice for a mute or an unmute of a lens."""
        if action.target_id.kind is not RefKind.LENS:
            raise ValueError("a notice tells viewers about a lens")
        match action.action:
            case ProducerActionType.SUPPRESS:
                kind = NoticeKind.PAUSED
            case ProducerActionType.RELEASE:
                kind = NoticeKind.RESUMED
            case _:
                raise ValueError(f"{action.action} does not pause or resume a lens")
        return cls(lens_id=action.target_id.id, kind=kind, clock_ms=action.clock_ms)


@dataclass
class _Mute:
    """One lens muted from `start_ms`, until `end_ms` if it has been undone."""

    action: ProducerAction
    start_ms: int
    end_ms: int | None = None

    def covers(self, clock_ms: int) -> bool:
        return self.start_ms <= clock_ms and (self.end_ms is None or clock_ms < self.end_ms)


class Mutes:
    def __init__(self) -> None:
        self._mutes: dict[str, list[_Mute]] = {}
        self._actions: list[ProducerAction] = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()  # a click arrives on one thread, a card on another

    def mute(self, lens_id: str, at_clock: int, actor: str, reason: str) -> ProducerAction:
        """Stop `lens_id`'s cards from `at_clock` on, and log it. Refused if it is muted."""
        calltrace.entered("Control")
        with self._lock:
            if self._open(lens_id) is not None:
                raise AlreadyMuted(lens_id)
            action = self._log(lens_id, ProducerActionType.SUPPRESS, at_clock, actor, reason)
            self._mutes.setdefault(lens_id, []).append(_Mute(action, at_clock))
            return action

    def unmute(self, lens_id: str, at_clock: int, actor: str, reason: str) -> ProducerAction:
        """Let `lens_id`'s cards through from `at_clock` on, and log it. Refused if not muted."""
        calltrace.entered("Control")
        with self._lock:
            mute = self._open(lens_id)
            if mute is None:
                raise NotMuted(lens_id)
            if at_clock < mute.start_ms:
                raise ValueError("a lens cannot be unmuted before it was muted")
            action = self._log(lens_id, ProducerActionType.RELEASE, at_clock, actor, reason)
            mute.end_ms = at_clock
            return action

    def is_muted(self, lens_id: str, at_clock: int) -> bool:
        """Whether `at_clock` is inside a mute of `lens_id`: from the mute to its unmute."""
        calltrace.entered("Control")
        with self._lock:
            return self._covers(lens_id, at_clock)

    def stops(self, lens_id: str, at_clock: int) -> bool:
        """Whether a card for the moment at `at_clock` is stopped, as it arrives or is judged.

        True if the moment is inside a mute, or if the lens is muted now (Q44: 2B).
        """
        calltrace.entered("Control")
        with self._lock:
            return self._open(lens_id) is not None or self._covers(lens_id, at_clock)

    def in_force(self, lens_id: str) -> ProducerAction | None:
        """The mute that is stopping `lens_id` now, or None."""
        with self._lock:
            mute = self._open(lens_id)
            return None if mute is None else mute.action

    def actions(self) -> list[ProducerAction]:
        """Every mute and unmute, in the order they were made."""
        with self._lock:
            return list(self._actions)

    def _open(self, lens_id: str) -> _Mute | None:
        mutes = self._mutes.get(lens_id, [])
        return mutes[-1] if mutes and mutes[-1].end_ms is None else None

    def _covers(self, lens_id: str, at_clock: int) -> bool:
        return any(mute.covers(at_clock) for mute in self._mutes.get(lens_id, []))

    def _log(
        self, lens_id: str, kind: ProducerActionType, at_clock: int, actor: str, reason: str
    ) -> ProducerAction:
        action = ProducerAction(
            action_id=f"pa-{next(self._ids)}",
            target_id=Ref(kind=RefKind.LENS, id=lens_id),
            action=kind,
            actor=actor,
            clock_ms=at_clock,
            reason=reason,
        )
        self._actions.append(action)
        return action
