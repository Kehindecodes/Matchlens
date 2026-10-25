"""What the producer view shows: the latest thing each lens did, told apart as spoke, quiet or
broken (P1, Q42).

The feed holds what the pipeline reports and derives nothing from the match. A lens that chose
silence has a suppressed rendition and a reason (invariant 11); a lens that failed has none, or
a `degraded` one. That is the whole difference, and the feed only reads it: the words and the
numbers on the page are the ones it is handed, not worked out in the browser.

Nothing here is sent to a viewer. The feed is not behind the viewer's release queue either: the
producer sees a lens's outcome when the pipeline has it, which is when a viewer on no delay
would see the card.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from matchlens.models import ClockMs, Lens, SuppressionReason
from matchlens.rendering import LensOutcome, MomentOutcome


class LensState(StrEnum):
    LISTENING = "listening"  # nothing has been put to the lens yet
    SPOKE = "spoke"  # the latest moment became a card
    QUIET = "quiet"  # the latest moment was a silence the lens chose
    ALARM = "alarm"  # silent because no claim held: the pipeline worked, the claims did not
    BROKEN = "broken"  # silent because it failed: no rendition, or a `degraded` one


# Which reasons are a lens's own choice, which are an alarm and which are a failure, from
# DATA-MODEL's table. `degraded` is a record rather than a gap since A5, but it is not a choice.
STATE_OF_REASON: dict[SuppressionReason, LensState] = {
    SuppressionReason.OUT_OF_SCOPE: LensState.QUIET,
    SuppressionReason.MUTED: LensState.QUIET,
    SuppressionReason.DEGRADED: LensState.BROKEN,
    SuppressionReason.VERIFICATION_FAILED: LensState.ALARM,
    SuppressionReason.CLAIMS_FILTERED_OUT: LensState.QUIET,
    SuppressionReason.BELOW_THRESHOLD: LensState.QUIET,
    SuppressionReason.RATE_LIMITED: LensState.QUIET,
}

_HEADLINE = {
    LensState.LISTENING: "Listening",
    LensState.SPOKE: "Spoke",
    LensState.QUIET: "Quiet by choice",
    LensState.ALARM: "Quiet, but not by choice",
    LensState.BROKEN: "Broken",
}

# One sentence per reason, for a producer. `importance`, `threshold`, `shown` and `limit` fill in
# the ones that are about numbers.
_WHY = {
    SuppressionReason.OUT_OF_SCOPE: "The moment is not about this lens's subject, so it was never "
    "a candidate.",
    SuppressionReason.MUTED: "A producer switched this lens off.",
    SuppressionReason.DEGRADED: "Rendering failed on this moment, so the lens had nothing it "
    "could say. It tries again on the next one.",
    SuppressionReason.VERIFICATION_FAILED: "Every claim for this moment failed verification, so "
    "there was nothing to say. A quality alarm: the claims did not hold.",
    SuppressionReason.CLAIMS_FILTERED_OUT: "None of the claims for this moment is a kind this "
    "lens shows. It drops them by design.",
    SuppressionReason.BELOW_THRESHOLD: "Importance {importance:.2f} is under this lens's "
    "threshold of {threshold:.2f}.",
    SuppressionReason.RATE_LIMITED: "Important enough ({importance:.2f}), but it has already "
    "shown {shown} of {limit} cards in the last 10 minutes.",
}


class LensView(BaseModel):
    """One lens as the producer sees it: the state and why, with the numbers behind it."""

    model_config = ConfigDict(frozen=True)

    lens_id: str
    name: str
    state: LensState
    headline: str  # the state in a few words
    why: str  # the reason in a sentence
    suppression_reason: SuppressionReason | None
    as_of_clock: ClockMs | None  # the match clock of the moment this describes
    importance: float | None  # what the lens judged that moment at
    threshold: float  # the lens's own, from its row
    shown_in_window: int | None  # cards shown in the ten match minutes to `as_of_clock`
    max_cards_per_10min: int


class ProducerSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    lenses: list[LensView]


class ProducerFeed:
    """The latest `LensView` of every lens, and a stream of them as they change.

    `receive` and `follow` belong to the event loop's thread: a pipeline on another thread hands
    its reports over with `loop.call_soon_threadsafe(feed.receive, ...)`.
    """

    def __init__(self, lens_rows: Sequence[Lens]) -> None:
        self._lenses = {lens.lens_id: lens for lens in lens_rows}
        self._views = {lens.lens_id: _listening(lens) for lens in lens_rows}
        self._waiters: set[asyncio.Event] = set()

    def receive(self, moment_outcome: MomentOutcome) -> None:
        """Take one moment's report: each lens it names shows that moment from now on."""
        answered = {outcome.lens_id: outcome for outcome in moment_outcome.outcomes}
        for lens_id in moment_outcome.lens_ids:
            self._views[lens_id] = _view(
                self._lenses[lens_id], moment_outcome, answered.get(lens_id)
            )
        for waiter in self._waiters:
            waiter.set()

    def snapshot(self) -> ProducerSnapshot:
        return ProducerSnapshot(lenses=list(self._views.values()))

    async def follow(self) -> AsyncIterator[ProducerSnapshot]:
        """The snapshot now, then again each time a report changes it."""
        changed = asyncio.Event()
        self._waiters.add(changed)
        try:
            while True:
                changed.clear()  # before reading, so a report during the send is not missed
                yield self.snapshot()
                await changed.wait()
        finally:
            self._waiters.discard(changed)


def _listening(lens: Lens) -> LensView:
    return LensView(
        lens_id=lens.lens_id,
        name=lens.name,
        state=LensState.LISTENING,
        headline=_HEADLINE[LensState.LISTENING],
        why="Nothing has been put to this lens yet.",
        suppression_reason=None,
        as_of_clock=None,
        importance=None,
        threshold=lens.importance_threshold,
        shown_in_window=None,
        max_cards_per_10min=lens.max_cards_per_10min,
    )


def _view(lens: Lens, moment_outcome: MomentOutcome, outcome: LensOutcome | None) -> LensView:
    """`lens` after one moment: the outcome it gave, or the lack of one."""
    if outcome is None:
        state, reason, why = LensState.BROKEN, None, _no_rendition(moment_outcome.failure)
        importance, shown = None, None
    else:
        reason = outcome.rendition.suppression_reason
        state = LensState.SPOKE if reason is None else STATE_OF_REASON[reason]
        importance, shown = outcome.importance, outcome.shown_in_window
        why = _why(lens, reason, outcome)
    return LensView(
        lens_id=lens.lens_id,
        name=lens.name,
        state=state,
        headline=_HEADLINE[state],
        why=why,
        suppression_reason=reason,
        as_of_clock=moment_outcome.clock_ms,
        importance=importance,
        threshold=lens.importance_threshold,
        shown_in_window=shown,
        max_cards_per_10min=lens.max_cards_per_10min,
    )


def _why(lens: Lens, reason: SuppressionReason | None, outcome: LensOutcome) -> str:
    if reason is None:
        return (
            f"Showed a card for the moment. Importance {outcome.importance:.2f}, "
            f"threshold {lens.importance_threshold:.2f}."
        )
    return _WHY[reason].format(
        importance=outcome.importance,
        threshold=lens.importance_threshold,
        shown=outcome.shown_in_window,
        limit=lens.max_cards_per_10min,
    )


def _no_rendition(failure: str | None) -> str:
    said = "No rendition was produced for this moment"
    return f"{said}: {failure}." if failure else f"{said}."
