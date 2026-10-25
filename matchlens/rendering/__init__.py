"""Turns one lens's selected claims into a rendition"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from matchlens import calltrace
from matchlens.explanation import Failure, Proposer
from matchlens.models import (
    Claim,
    DetailLevel,
    Lens,
    Metric,
    Moment,
    OverlayPacket,
    Rendition,
    SuppressionReason,
    Verification,
)
from matchlens.rendering import evidence, overlay, templates, writer
from matchlens.rendering.card import Card
from matchlens.rendering.evidence import ClaimEvidence
from matchlens.rendering.facts import clock, sentence
from matchlens.rendering.writer import Written
from matchlens.selection import Selection
from matchlens.verification.record import Record

__all__ = [
    "Card",
    "ClaimEvidence",
    "Written",
    "degraded",
    "drawer",
    "in_full",
    "overlay_packet",
    "render",
    "write",
]

# Reasons that outrank `degraded` (DATA-MODEL's evaluation order): a lens that was never a
# candidate, or was muted, says so even when Rendering failed.
_BEFORE_DEGRADED = (SuppressionReason.OUT_OF_SCOPE, SuppressionReason.MUTED)

# How many selected claims a lens speaks, by how much detail it wants. None is all of them.
_CLAIMS_SPOKEN = {DetailLevel.MINIMAL: 0, DetailLevel.STANDARD: 1, DetailLevel.FULL: None}


def render(
    moment: Moment,
    selection: Selection,
    lens: Lens,
    names: Mapping[str, str],
    written: Written | None = None,
) -> Rendition:
    """One rendition of `moment` for `lens`, written from templates and the selected claims.

    The words follow the moment's type and the lens's depth. Every number is the moment's clock
    or comes from a selected claim. `lens.detail_level` decides how many of the claims that have
    words are spoken, in the order the explainer made them; none is dropped here, because
    Selection already decided (D17). A selection with no claims is a suppressed rendition
    carrying Selection's reason (invariant 11). `names` maps a team or player id to what a
    viewer calls it.

    A lens with a `focus_team` is told the moment as for or against that side, and hears the
    score from that side and before any other claim, because that is where the moment leaves the
    side (D31, Q28: B). Any other comparison keeps the explainer's order (Q39). The claims are
    the same ones.

    `written` is what `write` got from a model for this selection (A4). It takes the place of
    the spoken claims' sentences, after the template's opening line, and the rendition says
    which model wrote it. Without it, the words are L3's alone: the seam A5 falls back on.
    """
    calltrace.entered("Rendering")
    if selection.suppression_reason is not None:
        return _suppressed(moment, lens, selection.suppression_reason)

    headline, opening, spoken = _words(
        moment, selection, lens, names, _CLAIMS_SPOKEN[lens.detail_level]
    )
    if written is None:
        body = " ".join([opening, *(text for _, text in spoken)])
        model, version = templates.MODEL, templates.MODEL_VERSION
    else:
        body = f"{opening} {written.text}"
        model, version = written.model, written.model_version
    return Rendition(
        **_base(moment, lens, tuple(claim.claim_id for claim in selection.claims)),
        headline=headline,
        body=body,
        suppressed=False,
        suppression_reason=None,
        model=model,
        model_version=version,
    )


def degraded(moment: Moment, selection: Selection, lens: Lens) -> Rendition:
    """The rendition for a lens Rendering failed on: below L1, so suppressed as `degraded`
    (A5, Q41: 1A). Still a record (invariant 11); like every suppressed rendition it carries
    no claims, and the claims Selection kept stay on the record through Audit."""
    reason = selection.suppression_reason
    if reason is None or reason not in _BEFORE_DEGRADED:
        reason = SuppressionReason.DEGRADED
    return _suppressed(moment, lens, reason)


def _base(moment: Moment, lens: Lens, claim_ids: tuple[str, ...]) -> dict[str, Any]:
    return {
        "rendition_id": f"{moment.moment_id}:{lens.lens_id}",
        "moment_id": moment.moment_id,
        "lens_id": lens.lens_id,
        "language": lens.language,
        "surviving_claim_ids": claim_ids,
        "rendered_at": datetime.now(UTC),
    }


def _suppressed(moment: Moment, lens: Lens, reason: SuppressionReason) -> Rendition:
    return Rendition(
        **_base(moment, lens, ()),
        headline=None,
        body=None,
        suppressed=True,
        suppression_reason=reason,
        model=templates.MODEL,
        model_version=templates.MODEL_VERSION,
    )


def write(
    moment: Moment,
    selection: Selection,
    lens: Lens,
    names: Mapping[str, str],
    model: Proposer,
) -> Written | Failure | None:
    """A model's words for the claims `render` would speak for this lens (A4), or the
    `Failure` of an answer the writer does not keep.

    The model is given those claims' sentences and nothing else, so a claim this lens dropped,
    or would leave unspoken, never reaches it. None, without a call, for a suppressed selection
    or one that speaks no claim.
    """
    if selection.suppression_reason is not None:
        return None
    _, _, spoken = _words(moment, selection, lens, names, _CLAIMS_SPOKEN[lens.detail_level])
    return writer.write([text for _, text in spoken], lens, names, model)


def in_full(moment: Moment, selection: Selection, lens: Lens, names: Mapping[str, str]) -> str:
    """The body `render` writes for this lens, with every selected claim spoken (D4).

    A catch-up line is the one place a lens says more than its card did: a late joiner is told
    how a goal came about even on a lens whose card only said it happened. The claims are still
    the ones Selection kept for this lens, read at its depth and from its side. Empty for a
    suppressed selection, which has nothing to say.
    """
    if selection.suppression_reason is not None:
        return ""
    _, opening, spoken = _words(moment, selection, lens, names, None)
    return " ".join([opening, *(text for _, text in spoken)])


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
    return overlay.packet(moment, lens, names, rendition, [claim for claim, _ in spoken])


def drawer(
    moment: Moment,
    selection: Selection,
    lens: Lens,
    names: Mapping[str, str],
    verifications: Sequence[Verification],
    record: Record,
) -> tuple[ClaimEvidence, ...]:
    """The evidence drawer for this lens's card of `moment` (A6): every claim Selection kept,
    marked whether the card said it, with the rows each cites and its verification."""
    _, _, spoken = _words(moment, selection, lens, names, _CLAIMS_SPOKEN[lens.detail_level])
    spoken_ids = {claim.claim_id for claim, _ in spoken}
    return evidence.drawer(selection.claims, spoken_ids, verifications, record, names)


def _words(
    moment: Moment,
    selection: Selection,
    lens: Lens,
    names: Mapping[str, str],
    limit: int | None,
) -> tuple[str, str, list[tuple[Claim, str]]]:
    """The headline, the opening line, and the claims spoken after it with their sentences.

    The claims spoken are the first `limit` that have words.
    """
    focus = lens.focus_team
    side = None if focus is None else "for" if moment.subject.id == focus else "against"
    words = templates.lookup(lens.language, moment.type, lens.depth, side)
    fields = {"team": names[moment.subject.id], "window": f"at {clock(moment.clock_ms)}"}
    if focus is not None:
        fields["focus"] = names[focus]
    claims = selection.claims if focus is None else _score_first(selection.claims)
    spoken = [
        (claim, text)
        for claim in claims
        if (text := sentence(claim, lens.depth, lens.language, names, focus)) is not None
    ][:limit]
    return words.headline.format(**fields), words.body.format(**fields), spoken


def _score_first(claims: tuple[Claim, ...]) -> list[Claim]:
    """`claims` with the score first, otherwise in the explainer's order."""
    return sorted(claims, key=lambda claim: not _is_score(claim))  # sorted is stable


def _is_score(claim: Claim) -> bool:
    """A goals comparison between the two sides: the score, and nothing else between them."""
    if len(claim.operands) != 2 or claim.operands[0].metric is not Metric.GOALS:
        return False
    return claim.operands[0].subject != claim.operands[1].subject
