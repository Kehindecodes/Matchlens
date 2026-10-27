"""A card as a packet a streaming player draws over the picture (D5, D34).

The template follows what the card says. A goal is a team card. A card that spoke a comparison
of one signal between the two sides is a stat bar, carrying the two numbers it said. Anything
else is a lower third: the headline and the line beneath it. A stat bar needs the card to have
said both numbers, so a depth that words the comparison without them is a lower third, and no
packet shows a number its card did not.

The payload is the renderer's fields, flat: names, words and the numbers the card spoke, as the
card wrote them ("58%"), never a calibrated value. No id, importance or reason reaches it. The
packet's own `rendition_id` is what traces it back.

It stays up for as long as it takes to read, between a floor and a ceiling.
"""

from collections.abc import Mapping, Sequence

from matchlens.config import settings
from matchlens.models import (
    Claim,
    Lens,
    Moment,
    MomentType,
    OverlayPacket,
    OverlayTemplate,
    Rendition,
)
from matchlens.rendering import templates
from matchlens.rendering.facts import clock, shown, told_from

Payload = dict[str, str | int | float]
_BETWEEN_SIDES = "vs_opponent"  # the form `facts` reads a signal compared across the sides as


def packet(
    moment: Moment,
    lens: Lens,
    names: Mapping[str, str],
    rendition: Rendition,
    spoken: Sequence[Claim],
) -> OverlayPacket:
    """The packet for a shown `rendition`, given the claims its body `spoken`, in order."""
    template, payload = _shape(moment, lens, names, rendition, spoken)
    return OverlayPacket(
        packet_id=f"{rendition.rendition_id}:overlay",
        rendition_id=rendition.rendition_id,
        display_at_clock=moment.clock_ms,
        duration_ms=duration(payload),
        template=template,
        payload=payload,
    )


def duration(payload: Mapping[str, str | int | float]) -> int:
    """How long it takes to read the payload's words, kept between the floor and the ceiling."""
    words = sum(len(v.split()) for v in payload.values() if isinstance(v, str))
    reading = words * settings.overlay_ms_per_word
    return max(settings.overlay_min_ms, min(settings.overlay_max_ms, reading))


def _shape(
    moment: Moment,
    lens: Lens,
    names: Mapping[str, str],
    rendition: Rendition,
    spoken: Sequence[Claim],
) -> tuple[OverlayTemplate, Payload]:
    assert rendition.headline is not None and rendition.body is not None  # a shown rendition
    text: Payload = {"headline": rendition.headline, "clock": clock(moment.clock_ms)}
    if moment.type in (MomentType.GOAL, MomentType.GOAL_DISALLOWED):
        team = names[moment.subject.id]
        return OverlayTemplate.TEAM_CARD, text | {"team": team, "body": rendition.body}
    for claim in spoken:
        if (stat := _stat(claim, lens, names)) is not None:
            return OverlayTemplate.STAT_BAR, text | stat
    return OverlayTemplate.LOWER_THIRD, text | {"body": rendition.body}


def _stat(claim: Claim, lens: Lens, names: Mapping[str, str]) -> Payload | None:
    """A signal compared between the two sides, read from the lens's side, or None.

    None too where the lens's depth says the comparison without its numbers ("pressing less
    than ..."): the bar would show figures the card never said.
    """
    if len(claim.operands) != 2:
        return None
    first, second = told_from(claim, lens.focus_team).operands
    words = templates.signal(lens.language, first.metric)
    if first.subject == second.subject or words is None:
        return None
    row = templates.fact(lens.language, first.metric, _BETWEEN_SIDES, lens.depth)
    if row is None or not {"value", "other_value"} <= templates.fields(row):
        return None
    value, other_value = shown(first.metric, first.value), shown(second.metric, second.value)
    if value is None or other_value is None:
        return None
    return {
        "label": words.label,
        "team": names[first.subject.id],
        "value": value,
        "other": names[second.subject.id],
        "other_value": other_value,
    }
