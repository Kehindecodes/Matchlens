"""Summarises what a lens would have shown before a viewer joined"""

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from matchlens import calltrace
from matchlens.config import settings
from matchlens.models import ClockMs, Lens, MomentType
from matchlens.rendering import Card


class CatchUpLine(BaseModel):
    """One card the lens showed, told in full, citing the moment and claims it is written from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rendition_id: str
    moment_id: str
    claim_ids: tuple[str, ...]
    clock_ms: ClockMs
    headline: str
    body: str


class CatchUp(BaseModel):
    """A stream message, like `Card`: sent, never stored."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lens_id: str
    from_clock: ClockMs
    to_clock: ClockMs
    lines: tuple[CatchUpLine, ...] = Field(min_length=1)  # nothing to say is no summary at all


def summarise(lens: Lens, cards: Iterable[Card], from_clock: int, to_clock: int) -> CatchUp | None:
    """What `lens` showed from `from_clock` to `to_clock`, both included, or None if nothing.

    A summary, never a replay (D4): the viewer is told about the cards their lens showed in the
    window and is sent none of them. Every lens is told the goals, each with how it came about
    and how it was scored, because that is what someone joining late wants first (Q30). A window
    with no goals is told its few most important moments instead. Each line is one card the lens
    showed, written from the claims Selection kept for that lens, at its depth and from its
    side, so nothing is said that the lens did not already stand behind (invariant 5).

    The claims have survived Selection, not verification: A3 is a stub, so nothing here says
    "verified". The same function over 0 to full time is X1's recap (D34).

    `cards` may hold any lens's cards and any clock; only this lens's, in the window, are read.
    """
    calltrace.entered("Catch-up")
    shown = [
        c
        for c in cards
        if c.rendition.lens_id == lens.lens_id and from_clock <= c.display_at_clock <= to_clock
    ]
    told = [c for c in shown if c.moment_type is MomentType.GOAL]
    if not told:
        # Most important first, the earlier on a tie, then told in the order they happened.
        ranked = sorted(shown, key=lambda c: (-c.importance, c.display_at_clock))
        told = ranked[: settings.catchup_key_moments]
    if not told:
        return None
    lines = tuple(
        CatchUpLine(
            rendition_id=c.rendition.rendition_id,
            moment_id=c.rendition.moment_id,
            claim_ids=c.rendition.surviving_claim_ids,
            clock_ms=c.display_at_clock,
            headline=c.rendition.headline or "",
            body=c.body_in_full,
        )
        for c in sorted(told, key=lambda c: c.display_at_clock)
    )
    return CatchUp(lens_id=lens.lens_id, from_clock=from_clock, to_clock=to_clock, lines=lines)
