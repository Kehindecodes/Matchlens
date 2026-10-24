"""Turns one lens's selected claims into a rendition"""

from collections.abc import Mapping
from datetime import UTC, datetime

from matchlens import calltrace
from matchlens.models import Claim, DetailLevel, Lens, Moment, OverlayPacket, Rendition
from matchlens.rendering import overlay, templates
from matchlens.rendering.card import Card
from matchlens.rendering.facts import clock, sentence
from matchlens.selection import Selection

__all__ = ["Card", "in_full", "overlay_packet", "render"]

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

    headline, body, _ = _words(moment, selection, lens, names, _CLAIMS_SPOKEN[lens.detail_level])
    return Rendition(
        **base,
        headline=headline,
        body=body,
        suppressed=False,
        suppression_reason=None,
    )


def in_full(moment: Moment, selection: Selection, lens: Lens, names: Mapping[str, str]) -> str:
    """The body `render` writes for this lens, with every selected claim spoken (D4).

    A catch-up line is the one place a lens says more than its card did: a late joiner is told
    how a goal came about even on a lens whose card only said it happened. The claims are still
    the ones Selection kept for this lens, read at its depth and from its side. Empty for a
    suppressed selection, which has nothing to say.
    """
    if selection.suppression_reason is not None:
        return ""
    return _words(moment, selection, lens, names, None)[1]


def overlay_packet(
    moment: Moment,
    selection: Selection,
    lens: Lens,
    names: Mapping[str, str],
    rendition: Rendition,
) -> OverlayPacket | None:
    """`rendition` as a packet for a player to draw over the picture, or None if suppressed (D5).

    Rendering writes it because it is the one stage that knows which claims the card spoke,
    and a stat bar may only show a number the card said.
    """
    if rendition.suppressed:
        return None
    _, _, spoken = _words(moment, selection, lens, names, _CLAIMS_SPOKEN[lens.detail_level])
    return overlay.packet(moment, lens, names, rendition, spoken)


def _words(
    moment: Moment,
    selection: Selection,
    lens: Lens,
    names: Mapping[str, str],
    limit: int | None,
) -> tuple[str, str, list[Claim]]:
    """The headline, the body, and the claims it spoke: the first `limit` that have words."""
    focus = lens.focus_team
    side = None if focus is None else "for" if moment.subject.id == focus else "against"
    words = templates.lookup(lens.language, moment.type, lens.depth, side)
    fields = {"team": names[moment.subject.id], "window": f"at {clock(moment.clock_ms)}"}
    if focus is not None:
        fields["focus"] = names[focus]
    claims = selection.claims if focus is None else _sides_first(selection.claims)
    spoken = [
        (claim, text)
        for claim in claims
        if (text := sentence(claim, lens.depth, lens.language, names, focus)) is not None
    ][:limit]
    body = " ".join([words.body.format(**fields), *(text for _, text in spoken)])
    return words.headline.format(**fields), body, [claim for claim, _ in spoken]


def _sides_first(claims: tuple[Claim, ...]) -> list[Claim]:
    """`claims` with the comparisons between two sides first, otherwise in the explainer's order."""
    return sorted(claims, key=lambda c: not _between_sides(c))  # sorted is stable


def _between_sides(claim: Claim) -> bool:
    return len(claim.operands) == 2 and claim.operands[0].subject != claim.operands[1].subject
