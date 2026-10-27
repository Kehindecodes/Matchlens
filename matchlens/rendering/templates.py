"""The template rows Rendering fills, read from committed data.

Rows are keyed on language, moment type and depth, never on a lens, so a lens is free to change
without a template changing (invariant 10). A lens with a `focus_team` reads the rows that also
carry a side, `for` when the moment's subject is the focus team and `against` when it is the
opponent: supporter-oriented, partisan in emphasis and neutral in voice (D31).

A row may carry `variants`, other ways to say the same thing. Which one a card gets is a
function of its own id (`variant_for`), so a repeat of a moment type does not repeat its wording,
and the same seed still says the same words (invariant 9).

A state row says what a moment did to the match: the score a goal left, a run of chances.

A fact row phrases one claim: it is keyed on the claim's metric, the form Rendering reads the
claim as (D30's wording rules), and the depth. The four signal metrics share the `signal` rows
and differ by the phrase their `signals` row gives. A claim whose form has no row is not
spoken, because a number nobody templated is a number nobody agreed to say. A signal metric may
also have rows of its own, which it reads before the shared ones.
"""

import json
import zlib
from dataclasses import dataclass
from pathlib import Path
from string import Formatter

from matchlens.models import Depth, Metric, MomentType

TEMPLATES_PATH = Path(__file__).with_name("templates.json")

MODEL = "templates"  # what a rendition's words came from when no model wrote them (invariant 7)
MODEL_VERSION = "templates-7"  # bump by hand whenever a row below changes what a card says

SIGNAL_ROWS = "signal"  # the fact rows the four signal metrics share

_HEADLINE_FIELDS = frozenset({"team", "window"})
_SIDED_FIELDS = _HEADLINE_FIELDS | {"focus"}  # a sided row may also name the focus team
SIDES = ("for", "against")
_FACT_FIELDS = frozenset(
    {"name", "other", "value", "other_value", "ordinal", "phrase", "label"}
    | {"minutes", "seconds", "until"}
)
# What a casual fact may say: names and words, never a number (L3).
CASUAL_FACT_FIELDS = frozenset({"name", "other", "ordinal", "phrase", "label"})
_PHRASES = ("up", "strong_up", "down", "strong_down")


@dataclass(frozen=True)
class Words:
    headline: str
    body: str


@dataclass(frozen=True)
class SignalWords:
    label: str
    phrases: dict[str, str]  # up, strong_up, down, strong_down


@dataclass(frozen=True)
class Templates:
    # the last key is the side; the value is every way the row can be said, the first the default
    headlines: dict[tuple[str, MomentType, Depth, str | None], tuple[Words, ...]]
    # what the moment did to the match (`state`), the headline that says it, and its variants
    states: dict[tuple[str, str, Depth, str | None], tuple[str, ...]]
    # language, metric or `signal`, form, depth
    facts: dict[tuple[str, str, str, Depth], tuple[str, ...]]
    signals: dict[tuple[str, Metric], SignalWords]
    ordinals: dict[str, tuple[str, ...]]
    number_words: dict[str, frozenset[str]]  # words that say a number, which A4 may not invent


def fields(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


def _checked(template: str, allowed: frozenset[str]) -> str:
    unknown = fields(template) - allowed
    if unknown:
        raise ValueError(
            f"template {template!r} uses {sorted(unknown)}, which Rendering never fills"
        )
    return template


def load(path: Path = TEMPLATES_PATH) -> Templates:
    """The rows in this file, each checked for the fields it uses."""
    data = json.loads(path.read_text())
    headlines = {}
    for row in data["headlines"]:
        side = row.get("side")
        if side is not None and side not in SIDES:
            raise ValueError(f"side {side!r} is not one of {SIDES}")
        allowed = _HEADLINE_FIELDS if side is None else _SIDED_FIELDS
        key = (row["language"], MomentType(row["moment_type"]), Depth(row["depth"]), side)
        headlines[key] = tuple(
            Words(_checked(spoken["headline"], allowed), _checked(spoken["body"], allowed))
            for spoken in (row, *row.get("variants", ()))
        )
    facts = {}
    for row in data.get("facts", []):
        depth = Depth(row["depth"])
        allowed = CASUAL_FACT_FIELDS if depth is Depth.CASUAL else _FACT_FIELDS
        if row["metric"] != SIGNAL_ROWS:
            Metric(row["metric"])  # a row for a metric that does not exist is a typo
        facts[(row["language"], row["metric"], row["form"], depth)] = tuple(
            _checked(text, allowed) for text in (row["text"], *row.get("variants", ()))
        )
    signals = {
        (row["language"], Metric(row["metric"])): SignalWords(
            row["label"], {phrase: row[phrase] for phrase in _PHRASES}
        )
        for row in data.get("signals", [])
    }
    ordinals = {lang: tuple(words) for lang, words in data.get("ordinals", {}).items()}
    number_words = {
        language: frozenset(words) for language, words in data.get("number_words", {}).items()
    }
    states = {
        (row["language"], row["state"], Depth(row["depth"]), row.get("side")): tuple(
            _checked(text, _SIDED_FIELDS if row.get("side") else _HEADLINE_FIELDS)
            for text in (row["headline"], *row.get("variants", ()))
        )
        for row in data.get("states", [])
    }
    return Templates(headlines, states, facts, signals, ordinals, number_words)


_TEMPLATES = load()


def variant_for(seed: str) -> int:
    """Which variant of a row `seed` gets. Stable across runs, unlike `hash`, which is salted."""
    return zlib.crc32(seed.encode())


def lookup(
    language: str, type_: MomentType, depth: Depth, side: str | None = None, pick: int = 0
) -> Words:
    """The words for this moment type at this depth, told from `side` if one is given.

    `pick` chooses among the row's variants, wrapping, so any integer is a valid choice.

    Raises `LookupError` if there are none. A sided lookup never falls back to the unsided row,
    because a team lens reading the match register would look like framing that worked.
    """
    try:
        variants = _TEMPLATES.headlines[(language, type_, depth, side)]
    except KeyError:
        told = f" told {side}" if side else ""
        raise LookupError(f"no template for {type_} at {depth}{told} in {language!r}") from None
    return variants[pick % len(variants)]


def state_headline(
    language: str, state: str, depth: Depth, pick: int = 0, side: str | None = None
) -> str | None:
    """The headline for a moment that left the match in `state`, or None if nobody has said.

    It says what the moment meant, so it replaces the template's opening rather than adding to it.
    Told from `side` of a lens that follows one, it reads the row for that side if there is one,
    and the side-neutral row if there is not.
    """
    variants = _TEMPLATES.states.get((language, state, depth, side)) or _TEMPLATES.states.get(
        (language, state, depth, None)
    )
    return None if variants is None else variants[pick % len(variants)]


def fact(language: str, metric: Metric, form: str, depth: Depth, pick: int = 0) -> str | None:
    """How to phrase a claim on `metric` read as `form` at `depth`, or None if nobody has said.

    A signal metric's own row comes first, then the row the four signals share. `pick` chooses
    among the row's variants, wrapping.
    """
    variants = _TEMPLATES.facts.get((language, metric.value, form, depth))
    if variants is None and (language, metric) in _TEMPLATES.signals:
        variants = _TEMPLATES.facts.get((language, SIGNAL_ROWS, form, depth))
    return None if variants is None else variants[pick % len(variants)]


def signal(language: str, metric: Metric) -> SignalWords | None:
    """The label and phrases for a signal metric, or None for a metric that is not a signal."""
    return _TEMPLATES.signals.get((language, metric))


def ordinal(language: str, n: float) -> str | None:
    """ "first" for 1, and so on, or None where there is no word for `n`."""
    words = _TEMPLATES.ordinals.get(language, ())
    return words[int(n) - 1] if n.is_integer() and 1 <= n <= len(words) else None


def number_words(language: str) -> frozenset[str] | None:
    """The words that say a number in `language`, or None if nobody has listed them."""
    return _TEMPLATES.number_words.get(language)
