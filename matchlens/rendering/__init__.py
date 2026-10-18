"""Turns one lens's selected claims into a rendition"""

from collections.abc import Sequence
from datetime import UTC, datetime

from matchlens import calltrace
from matchlens.models import Claim, Lens, Moment, Rendition
from matchlens.rendering.card import Card

__all__ = ["SKELETON_BODY", "SKELETON_HEADLINE", "Card", "render"]

# S4's constant card. Deliberately says nothing about the match: it has no verified claims behind
# it, so it must not assert anything (invariant 5). L3 replaces it with template renditions.
SKELETON_HEADLINE = "The walking skeleton"
SKELETON_BODY = "This card went from the seeded match through every stage to your screen."


def render(moment: Moment, selected: Sequence[Claim], lens: Lens) -> Rendition:
    """One rendition of `moment` for `lens`. Stub: the S4 constant card until L3."""
    calltrace.entered("Rendering")
    return Rendition(
        rendition_id=f"{moment.moment_id}:{lens.lens_id}",
        moment_id=moment.moment_id,
        lens_id=lens.lens_id,
        language=lens.language,
        headline=SKELETON_HEADLINE,
        body=SKELETON_BODY,
        surviving_claim_ids=tuple(c.claim_id for c in selected),
        suppressed=False,
        suppression_reason=None,
        rendered_at=datetime.now(UTC),
    )
