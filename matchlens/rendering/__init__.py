"""Turns one lens's selected claims into a rendition"""

from collections.abc import Mapping
from datetime import UTC, datetime

from matchlens import calltrace
from matchlens.models import Claim, DetailLevel, Lens, Moment, Rendition
from matchlens.rendering import templates
from matchlens.rendering.card import Card
from matchlens.selection import Selection

__all__ = ["Card", "render"]

# How many selected claims a lens speaks, by how much detail it wants. None is all of them.
_CLAIMS_SPOKEN = {DetailLevel.MINIMAL: 0, DetailLevel.STANDARD: 1, DetailLevel.FULL: None}


def render(
    moment: Moment, selection: Selection, lens: Lens, team_names: Mapping[str, str]
) -> Rendition:
    """One rendition of `moment` for `lens`, written from templates and the selected claims.

    The words follow the moment's type and the lens's depth. Every number comes from a selected
    claim and is written as the claim holds it. `lens.detail_level` decides how many of those
    claims are spoken; none is dropped here, because Selection already decided (D17). A
    selection with no claims is a suppressed rendition carrying Selection's reason (invariant
    11). `team_names` maps a team id to what a viewer calls it.
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

    words = templates.lookup(lens.language, moment.type, lens.depth)
    fields = {"team": team_names[moment.subject.id], "window": _window(selection.claims[0])}
    return Rendition(
        **base,
        headline=words.headline.format(**fields),
        body=" ".join([words.body.format(**fields), *_facts(selection.claims, lens)]),
        suppressed=False,
        suppression_reason=None,
    )


def _facts(claims: tuple[Claim, ...], lens: Lens) -> list[str]:
    """One sentence per spoken claim that has a template, up to what the lens's detail allows."""
    limit = _CLAIMS_SPOKEN[lens.detail_level]
    lines = []
    for claim in claims:
        if limit is not None and len(lines) >= limit:
            break
        template = templates.fact(lens.language, claim.operands[0].metric)
        if template is not None and len(claim.operands) == 1:
            lines.append(template.format(value=_number(claim.operands[0].value)))
    return lines


def _window(claim: Claim) -> str:
    window = claim.operands[0].window
    if window.start_ms == window.end_ms:
        return f"at {_clock(window.end_ms)}"
    return f"from {_clock(window.start_ms)} to {_clock(window.end_ms)}"


def _clock(ms: int) -> str:
    return f"{ms // 60_000}:{ms // 1000 % 60:02d}"


def _number(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"
