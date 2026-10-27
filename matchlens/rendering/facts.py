"""One claim as one sentence: D30's wording rules, read from the claim alone.

Each claim is read as a form, the wording its values allow: a goal claim on a player is the
scorer, a shot of quality 0.25 or more is a big chance, a move from winning the ball to the shot
in 20 s or less is a quick attack. The rules read only what the claim holds, so the words can
never say more than the evidence the claim cites. A claim the rules have no form for is not
spoken.

A viewer is never shown a calibrated value: not a shot's quality, not a sum of them, not a
standard deviation. Those claims are said in words only, and their `value` field is empty, so a
row that asked for one would not be spoken at all. The plain ratios are shown in a form a viewer
can read: a share as a percentage, passes allowed per defensive action to one decimal place.

Told from a focus team, a comparison whose second operand is that team is read the other way
round, so "Oakhurst lead 2–1" becomes "Redfern trail 1–2" (D31). The claim is not changed: the
reversed copy is only read here, never stored or passed on.
"""

from collections.abc import Mapping

from matchlens.config import settings
from matchlens.models import Claim, ClaimType, Depth, Metric, RefKind
from matchlens.rendering import templates


def sentence(
    claim: Claim,
    depth: Depth,
    language: str,
    names: Mapping[str, str],
    focus: str | None = None,
    pick: int = 0,
    side: str | None = None,
) -> str | None:
    """`claim` as one sentence at `depth`, or None if it is not one this depth speaks.

    `focus` is the team id a lens follows, if it follows one, and `side` whether the moment is
    for or against it: a save reads "saved by" for the side that shot and "makes the save" for the
    side that kept it out, so a form may have a row for each, `saved_for` and `saved_against`.
    `pick` chooses among the row's variants (`templates.variant_for`).
    """
    claim = _leader_first(told_from(claim, focus))
    read = _read(claim, language)
    if read is None:
        return None
    form, values = read
    metric = claim.operands[0].metric
    text = (side and templates.fact(language, metric, f"{form}_{side}", depth, pick)) or (
        templates.fact(language, metric, form, depth, pick)
    )
    if text is None:
        return None
    filled = {**_fields(claim, language, names), **values}
    if any(filled.get(name) is None for name in templates.fields(text)):
        return None  # e.g. no word for the twelfth: say nothing rather than a number in words
    said = text.format(**filled)
    return said[0].upper() + said[1:]  # a row may open on a label: "possession share ..."


def told_from(claim: Claim, focus: str | None) -> Claim:
    """`claim` with the focus team's operand first, if it compares the focus team with another."""
    if focus is None or len(claim.operands) != 2:
        return claim
    first, second = claim.operands
    if second.subject.id != focus or first.subject.id == focus:
        return claim
    return claim.model_copy(update={"operands": (second, first)})


def _leader_first(claim: Claim) -> Claim:
    """A comparison of the two sides' big chances, read from the side with more of them."""
    if len(claim.operands) != 2 or claim.operands[0].metric is not Metric.CHANCES:
        return claim
    first, second = claim.operands
    if second.value <= first.value:
        return claim
    return claim.model_copy(update={"operands": (second, first)})


def _read(claim: Claim, language: str) -> tuple[str, Mapping[str, str | None]] | None:
    """The form `claim` reads as, and any words the form brings, or None if it has none."""
    subject, *other = claim.operands
    metric, value = subject.metric, subject.value
    words = templates.signal(language, metric)
    if words is not None:
        return _signal(claim, words)
    if metric is Metric.GOALS:
        if other:
            against = other[0].value
            return ("ahead" if value > against else "level" if value == against else "behind"), {}
        if subject.subject.kind is RefKind.PLAYER:
            return ("scorer_first" if value == 1 else "scorer_again"), {}
        return "team_goals", {}
    if metric is Metric.BALL_WON_THIRD:
        return {3: "won_high", 2: "won_middle", 1: "won_deep"}[int(value)], {}
    if metric is Metric.BALL_LOST:
        return "lost", {}
    if metric is Metric.BALL_LOST_BY_KEEPER:
        return "keeper_lost", {}
    if metric is Metric.PRESSURED_LOSS:
        return "pressured", {}
    if metric is Metric.SWITCH_OF_PLAY:
        return "switch", {}
    if metric is Metric.REGAIN:
        return "regain", {}
    if metric is Metric.COMBINATION:
        return "combination", {}
    if metric is Metric.OVERLOAD:
        return "overload", {}
    if metric is Metric.DECOY_RUN:
        return "decoy", {}
    if metric is Metric.EARLY_RUN:
        return "early", {}
    if metric is Metric.ASSIST:
        return "assist", {}
    if metric is Metric.SHOT_SAVED_BY:
        return "saved", {}
    if metric is Metric.SHOT_BLOCKED_BY:
        return "blocked", {}
    if metric is Metric.SHOT_DISTANCE:
        close, far = settings.wording_close_range_m, settings.wording_long_range_m
        return ("close" if value <= close else "long" if value >= far else "mid"), {}
    if metric is Metric.SHOT_QUALITY:
        return ("big" if value >= settings.spotter_chance_quality else "hard"), {}
    if metric is Metric.CHANCES:
        if other:  # the run set against the other side's: only a clear edge is worth saying
            ratio = settings.wording_chance_edge_ratio
            clear = value >= settings.wording_chance_run and value >= ratio * other[0].value
            return ("edge", {}) if clear else None
        return ("run", {}) if value >= settings.wording_chance_run else None
    if metric is Metric.BUILD_UP_PASSES:
        width = subject.window.end_ms - subject.window.start_ms
        if width <= settings.wording_quick_attack_ms:
            return ("quick_single" if value == 1 else "quick"), {}
        return ("patient", {}) if value >= settings.wording_patient_passes else None
    return None


def _signal(
    claim: Claim, words: templates.SignalWords
) -> tuple[str, Mapping[str, str | None]] | None:
    subject, *other = claim.operands
    label = {"label": words.label}
    if claim.claim_type is ClaimType.INTERPRETIVE:
        assert claim.threshold is not None  # an interpretive claim always carries one
        strong = abs(claim.threshold) >= settings.claim_strong_z
        way = "up" if claim.threshold > 0 else "down"
        return "judged", label | {"phrase": words.phrases[f"strong_{way}" if strong else way]}
    if not other or other[0].value == subject.value:
        return None  # no difference has no direction to say
    way = "up" if subject.value > other[0].value else "down"
    form = "vs_earlier" if other[0].subject == subject.subject else "vs_opponent"
    return form, label | {"phrase": words.phrases[way]}


def _fields(claim: Claim, language: str, names: Mapping[str, str]) -> dict[str, str | None]:
    """What every form may use: names, values and the windows, as the claim holds them."""
    subject, *other = claim.operands
    width = subject.window.end_ms - subject.window.start_ms
    filled: dict[str, str | None] = {
        "name": names[subject.subject.id],
        "value": shown(subject.metric, subject.value),
        "ordinal": templates.ordinal(language, subject.value),
        "minutes": number(round(width / 60_000)),
        "seconds": number(round(width / 1000)),
        "other": None,
        "other_value": None,
        "until": None,
    }
    if other:
        filled |= {
            "other": names[other[0].subject.id],
            "other_value": shown(other[0].metric, other[0].value),
            "until": clock(other[0].window.end_ms),
        }
    return filled


_CALIBRATED = frozenset({Metric.SHOT_QUALITY, Metric.CHANCE_QUALITY})  # said in words only
_SHARES = frozenset({Metric.TERRITORY, Metric.POSSESSION_CONTROL})  # 0–1, shown as a percentage


def shown(metric: Metric, value: float) -> str | None:
    """`value` as a viewer reads it, or None for a calibrated value, which a viewer never sees."""
    if metric in _CALIBRATED:
        return None
    if metric in _SHARES:
        return f"{round(value * 100)}%"
    if metric is Metric.PRESSING_INTENSITY:
        return number(round(value, 1))
    return number(value)


def clock(ms: int) -> str:
    return f"{ms // 60_000}:{ms // 1000 % 60:02d}"


def number(value: float) -> str:
    """A value as the claim holds it, to two places at most: 0.41, not 0.413672."""
    rounded = round(float(value), 2)
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:g}"
