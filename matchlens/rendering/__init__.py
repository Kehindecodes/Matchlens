"""Turns one lens's selected claims into a rendition"""

from collections.abc import Mapping
from datetime import UTC, datetime

from matchlens import calltrace
from matchlens.models import Claim, DetailLevel, Lens, Moment, Rendition
from matchlens.rendering import templates
from matchlens.rendering.card import Card
from matchlens.rendering.facts import clock, sentence
from matchlens.selection import Selection

__all__ = ["Card", "render"]

# How many selected claims a lens speaks, by how much detail it wants. None is all of them.
_CLAIMS_SPOKEN = {DetailLevel.MINIMAL: 0, DetailLevel.STANDARD: 1, DetailLevel.FULL: None}


def render(moment: Moment, selection: Selection, lens: Lens, names: Mapping[str, str]) -> Rendition:
    """One rendition of `moment` for `lens`, written from templates and the selected claims.

    The words follow the moment's type and the lens's depth. Every number is the moment's clock
    or comes from a selected claim. `lens.detail_level` decides how many of the claims that have
    words are spoken, in the order the explainer made them; none is dropped here, because
    Selection already decided (D17). A selection with no claims is a suppressed rendition
    carrying Selection's reason (invariant 11). `names` maps a team or player id to what a
    viewer calls it.

    A lens with a `focus_team` is told the moment as for or against that side, and hears a
    comparison between the two sides from that side and before any other claim, because that is
    where the moment leaves the side (D31, Q28: B). The claims are the same ones.
    """
    calltrace.entered("Rendering")
    base = {
        "rendition_id": f"{moment.moment_id}:{lens.lens_id}",
        "moment_id": moment.moment_id,
        "lens_id": lens.lens_id,
        "language": lens.language,
        "surviving_claim_ids": tuple(c.claim_id for c in selection.claims),
        "rendered_at": datetime.now(UTC),
    }
    if selection.suppression_reason is not None:
        return Rendition(
            **base,
            headline=None,
            body=None,
            suppressed=True,
            suppression_reason=selection.suppression_reason,
        )

    focus = lens.focus_team
    side = None if focus is None else "for" if moment.subject.id == focus else "against"
    words = templates.lookup(lens.language, moment.type, lens.depth, side)
    fields = {"team": names[moment.subject.id], "window": f"at {clock(moment.clock_ms)}"}
    if focus is not None:
        fields["focus"] = names[focus]
    limit = _CLAIMS_SPOKEN[lens.detail_level]
    claims = selection.claims if focus is None else _sides_first(selection.claims)
    spoken = [
        text
        for claim in claims
        if (text := sentence(claim, lens.depth, lens.language, names, focus)) is not None
    ][:limit]
    return Rendition(
        **base,
        headline=words.headline.format(**fields),
        body=" ".join([words.body.format(**fields), *spoken]),
        suppressed=False,
        suppression_reason=None,
    )


def _sides_first(claims: tuple[Claim, ...]) -> list[Claim]:
    """`claims` with the comparisons between two sides first, otherwise in the explainer's order."""
    return sorted(claims, key=lambda c: not _between_sides(c))  # sorted is stable


def _between_sides(claim: Claim) -> bool:
    return len(claim.operands) == 2 and claim.operands[0].subject != claim.operands[1].subject
