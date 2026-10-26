"""Turns one lens's selected claims into a rendition"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from matchlens import calltrace
from matchlens.config import settings
from matchlens.explanation import Failure, Proposer
from matchlens.models import (
    Claim,
    Depth,
    DetailLevel,
    Lens,
    Metric,
    Moment,
    MomentType,
    OverlayPacket,
    RefKind,
    Rendition,
    SuppressionReason,
)
from matchlens.rendering import overlay, state, templates, writer
from matchlens.rendering.card import Card
from matchlens.rendering.facts import clock, sentence
from matchlens.rendering.outcomes import LensOutcome, MomentOutcome
from matchlens.rendering.writer import Written
from matchlens.selection import Selection

__all__ = [
    "Card",
    "LensOutcome",
    "MomentOutcome",
    "Written",
    "degraded",
    "in_full",
    "overlay_packet",
    "render",
    "write",
]

# Reasons that outrank `degraded` (DATA-MODEL's evaluation order): a lens that was never a
# candidate, or was muted, says so even when Rendering failed.
_BEFORE_DEGRADED = (SuppressionReason.OUT_OF_SCOPE, SuppressionReason.MUTED)


def _spoken(lens: Lens) -> int:
    """How many selected claims a card speaks, by how much detail the lens wants. A card is read
    in seconds, so even the fullest lens speaks a few; Catch-up's `in_full` speaks them all."""
    match lens.detail_level:
        case DetailLevel.MINIMAL:
            return 0
        case DetailLevel.STANDARD:
            return 1
        case DetailLevel.FULL:
            return settings.claims_spoken_full


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

    headline, opening, spoken = _words(moment, selection, lens, names, _spoken(lens))
    if written is None:
        body = _joined(opening, [text for _, text in spoken])
        model, version = templates.MODEL, templates.MODEL_VERSION
    else:
        body = _joined(opening, [written.text])
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
    _, _, spoken = _words(moment, selection, lens, names, _spoken(lens))
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
    return _joined(opening, [text for _, text in spoken])


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
    _, _, spoken = _words(moment, selection, lens, names, _spoken(lens))
    return overlay.packet(moment, lens, names, rendition, [claim for claim, _ in spoken])


def _joined(opening: str, sentences: list[str]) -> str:
    """The opening line, if there is one, then the sentences, as one body."""
    return " ".join(part for part in (opening, *sentences) if part)


def _words(
    moment: Moment,
    selection: Selection,
    lens: Lens,
    names: Mapping[str, str],
    limit: int | None,
) -> tuple[str, str, list[tuple[Claim, str]]]:
    """The headline, the opening line, and the claims spoken after it with their sentences.

    The claims spoken are the first `limit` that have words, in the order that tells this lens's
    viewer most. The card has to be understood alone, so its first clause carries the news:

    - a goal that left the match in a state the claims show (it levelled it, it went further
      ahead) is headlined by that state, told for or against the side a lens follows; the same
      for a chance that is one of a run. The viewer has seen the goal and wants to know what it
      did, so there is no opening line.
    - a tactical shift has no news but what moved, so its first spoken fact is its headline.
    - anything else keeps the template's headline.

    A lens that follows a side speaks only where the side stands, but only on its card: a late
    joiner's catch-up (`limit` None, D4) is told how it came about too.
    """
    focus = lens.focus_team
    pick = templates.variant_for(moment.moment_id)
    side = None if focus is None else "for" if moment.subject.id == focus else "against"
    fields = {"team": names[moment.subject.id], "window": f"at {clock(moment.clock_ms)}"}
    if focus is not None:
        fields["focus"] = names[focus]
    spoken = [
        (claim, text)
        for claim in _in_order(selection.claims, moment, lens, pick)
        if (focus is None or not _names_their_player(claim, moment, side))
        and (focus is None or limit is None or _for_a_supporter(claim, moment))
        and (
            text := sentence(
                claim,
                lens.depth,
                lens.language,
                names,
                focus,
                templates.variant_for(claim.claim_id),
                side,
            )
        )
        is not None
    ][:limit]

    headline = opening = None
    if (named := _state(moment, selection.claims)) is not None:
        said = templates.state_headline(lens.language, named, lens.depth, pick, side)
        if said is not None:
            headline, opening = said.format(**fields), ""
    if headline is None and moment.type is MomentType.TACTICAL_SHIFT and _judges(spoken, lens):
        (_, headline), *spoken = spoken
        spoken, opening = spoken[:1], ""  # what moved, then once against the other side
    if headline is None or opening is None:
        words = templates.lookup(lens.language, moment.type, lens.depth, side, pick)
        headline, opening = words.headline.format(**fields), words.body.format(**fields)
    return headline, opening, spoken


def _judges(spoken: list[tuple[Claim, str]], lens: Lens) -> bool:
    """Whether the first thing a shift card says is a judgement of one signal, which is news
    enough to be the card's first clause; a comparison alone is not."""
    if not spoken:
        return False
    first = spoken[0][0]
    return (
        len(first.operands) == 1
        and templates.signal(lens.language, first.operands[0].metric) is not None
    )


def _state(moment: Moment, claims: tuple[Claim, ...]) -> str | None:
    if moment.type is MomentType.GOAL:
        return state.goal_state(moment, claims)
    if moment.type is MomentType.CHANCE:
        return state.chance_state(claims)
    return None


# How a goal or a chance came about, in the order each viewer wants it. A casual viewer is told
# who gave it away and where it was won, a person and a place; one who wants the mechanism is
# told where it was won, how fast it was punished and how far out it was struck, and the person
# after. A depth that is not casual is the second: the order is a register, not a lens (D31).
_HOW_CASUAL = (Metric.BALL_WON_THIRD, Metric.ASSIST, Metric.SHOT_DISTANCE)  # then the build-up
_HOW_CLOSER = (
    Metric.BALL_WON_THIRD,
    Metric.BUILD_UP_PASSES,
    Metric.ASSIST,
    Metric.SHOT_DISTANCE,
    Metric.BALL_LOST,
)


def _names_their_player(claim: Claim, moment: Moment, side: str | None) -> bool:
    """Whether `claim` names a player of the side the lens does not follow, which it never says.

    A supporter is told their own side's players: who scored for them, who set it up, who gave
    the ball away to the other side's goal, who saved or blocked the other side's shot. The
    other side's scorer, assist and stopper are the other side's, so which they are follows from
    whether the moment is for or against the side, and needs no roster.
    """
    metric = claim.operands[0].metric
    scorer = metric is Metric.GOALS and claim.operands[0].subject.kind is RefKind.PLAYER
    if moment.type is MomentType.GOAL:
        if side == "for":
            return metric in (Metric.BALL_LOST, Metric.BALL_LOST_BY_KEEPER)
        return scorer or metric is Metric.ASSIST
    if moment.type is MomentType.CHANCE and side == "for":
        return metric in _STOPPERS
    return False


def _for_a_supporter(claim: Claim, moment: Moment) -> bool:
    """What a lens that follows a side speaks: what happened to its side, and who did it.

    A goal: the score it left, who scored, who set it up, and who gave the ball away for it. A
    chance: the run it is part of, and who saved or blocked it. A shift: what moved. How the move
    began, or how far out the shot was, is for the lenses that want the mechanism.
    """
    first = claim.operands[0]
    if moment.type is MomentType.GOAL:
        scorer = first.metric is Metric.GOALS and first.subject.kind is RefKind.PLAYER
        return _is_score(claim) or scorer or first.metric in _GOAL_PEOPLE
    if moment.type is MomentType.CHANCE:
        return first.metric is Metric.CHANCES or first.metric in _STOPPERS
    return True


_GOAL_PEOPLE = frozenset({Metric.ASSIST, Metric.BALL_LOST, Metric.BALL_LOST_BY_KEEPER})
_STOPPERS = frozenset({Metric.SHOT_SAVED_BY, Metric.SHOT_BLOCKED_BY})


def _in_order(claims: tuple[Claim, ...], moment: Moment, lens: Lens, pick: int = 0) -> list[Claim]:
    """`claims` in the order a card should speak them, otherwise in the explainer's order.

    A lens that follows a side hears the score first where a goal leaves that side (D31, Q28:
    B); a lens that does not already has the score on the scoreboard, so it hears it last. A
    shift is heard as a judgement, then against the other side, then against itself earlier.
    Every other claim keeps its place (Q39).
    """
    return sorted(claims, key=lambda claim: _rank(claim, moment, lens, pick))  # stable


def _rank(claim: Claim, moment: Moment, lens: Lens, pick: int) -> int:
    first = claim.operands[0]
    if moment.type is MomentType.TACTICAL_SHIFT:
        if len(claim.operands) == 2:
            return 1 if first.subject != claim.operands[1].subject else 2
        return 0
    if moment.type is MomentType.GOAL and _is_score(claim):
        return 0 if lens.focus_team is not None else 90
    if lens.focus_team is not None and moment.type is MomentType.GOAL:
        # Where it leaves the side, then who scored, who set it up, and who gave it away.
        scorer = first.metric is Metric.GOALS and first.subject.kind is RefKind.PLAYER
        people = (Metric.ASSIST, Metric.BALL_LOST_BY_KEEPER, Metric.BALL_LOST)
        if scorer:
            return 1
        if first.metric in people:
            return 2 + people.index(first.metric)
    if first.metric is Metric.CHANCES:
        return 0 if len(claim.operands) == 1 else 1
    if first.metric in _STOPPERS:
        return 2
    order = _HOW_CLOSER
    if lens.depth is Depth.CASUAL:
        turn = pick % len(_HOW_CASUAL)  # a different first fact each time, so no card repeats
        order = (*_HOW_CASUAL[turn:], *_HOW_CASUAL[:turn], Metric.BUILD_UP_PASSES)
    if first.metric in order:
        return 10 + order.index(first.metric)
    return 50


def _is_score(claim: Claim) -> bool:
    """A goals comparison between the two sides: the score, and nothing else between them."""
    if len(claim.operands) != 2 or claim.operands[0].metric is not Metric.GOALS:
        return False
    return claim.operands[0].subject != claim.operands[1].subject
