"""Turns one lens's selected claims into a rendition"""

from datetime import UTC, datetime

from matchlens import calltrace
from matchlens.models import Lens, Moment, Rendition
from matchlens.rendering.card import Card
from matchlens.selection import Selection

__all__ = ["SKELETON_BODY", "SKELETON_HEADLINE", "Card", "render"]

# S4's constant card. Deliberately says nothing about the match: it has no verified claims behind
# it, so it must not assert anything (invariant 5). L3 replaces it with template renditions.
SKELETON_HEADLINE = "The walking skeleton"
SKELETON_BODY = "This card went from the seeded match through every stage to your screen."


def render(moment: Moment, selection: Selection, lens: Lens) -> Rendition:
    """One rendition of `moment` for `lens`. Stub: the S4 constant card until L3.

    A selection with no claims comes out as a suppressed rendition carrying Selection's reason
    (invariant 11), never a card.
    """
    calltrace.entered("Rendering")
    silent = selection.suppression_reason is not None
    return Rendition(
        rendition_id=f"{moment.moment_id}:{lens.lens_id}",
        moment_id=moment.moment_id,
        lens_id=lens.lens_id,
        language=lens.language,
        headline=None if silent else SKELETON_HEADLINE,
        body=None if silent else SKELETON_BODY,
        surviving_claim_ids=tuple(c.claim_id for c in selection.claims),
        suppressed=silent,
        suppression_reason=selection.suppression_reason,
        rendered_at=datetime.now(UTC),
    )
