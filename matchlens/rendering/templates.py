"""The template rows Rendering fills, read from committed data.

Rows are keyed on language, moment type and depth, never on a lens, so a lens is free to change
without a template changing (invariant 10). A fact row phrases one claim: it is keyed on the
claim's metric, the form Rendering reads the claim as (D30's wording rules), and the depth. The
four signal metrics share the `signal` rows and differ by the phrase their `signals` row gives.
A claim whose form has no row is not spoken, because a number nobody templated is a number
nobody agreed to say.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from string import Formatter

from matchlens.models import Depth, Metric, MomentType

TEMPLATES_PATH = Path(__file__).with_name("templates.json")

SIGNAL_ROWS = "signal"  # the fact rows the four signal metrics share

_HEADLINE_FIELDS = frozenset({"team", "window"})
_FACT_FIELDS = frozenset(
    {"name", "other", "value", "other_value", "ordinal", "phrase", "label"}
    | {"minutes", "seconds", "until", "sigma"}
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
    headlines: dict[tuple[str, MomentType, Depth], Words]
    facts: dict[tuple[str, str, str, Depth], str]  # language, metric or `signal`, form, depth
    signals: dict[tuple[str, Metric], SignalWords]
    ordinals: dict[str, tuple[str, ...]]


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
    headlines = {
        (row["language"], MomentType(row["moment_type"]), Depth(row["depth"])): Words(
            _checked(row["headline"], _HEADLINE_FIELDS), _checked(row["body"], _HEADLINE_FIELDS)
        )
        for row in data["headlines"]
    }
    facts = {}
    for row in data.get("facts", []):
        depth = Depth(row["depth"])
        allowed = CASUAL_FACT_FIELDS if depth is Depth.CASUAL else _FACT_FIELDS
        if row["metric"] != SIGNAL_ROWS:
            Metric(row["metric"])  # a row for a metric that does not exist is a typo
        facts[(row["language"], row["metric"], row["form"], depth)] = _checked(row["text"], allowed)
    signals = {
        (row["language"], Metric(row["metric"])): SignalWords(
            row["label"], {p: row[p] for p in _PHRASES}
        )
        for row in data.get("signals", [])
    }
    ordinals = {lang: tuple(words) for lang, words in data.get("ordinals", {}).items()}
    return Templates(headlines, facts, signals, ordinals)


_TEMPLATES = load()


def lookup(language: str, type_: MomentType, depth: Depth) -> Words:
    """The words for this moment type at this depth. Raises `LookupError` if there are none."""
    try:
        return _TEMPLATES.headlines[(language, type_, depth)]
    except KeyError:
        raise LookupError(f"no template for {type_} at {depth} in {language!r}") from None


def fact(language: str, metric: Metric, form: str, depth: Depth) -> str | None:
    """How to phrase a claim on `metric` read as `form` at `depth`, or None if nobody has said."""
    key = SIGNAL_ROWS if (language, metric) in _TEMPLATES.signals else metric.value
    return _TEMPLATES.facts.get((language, key, form, depth))


def signal(language: str, metric: Metric) -> SignalWords | None:
    """The label and phrases for a signal metric, or None for a metric that is not a signal."""
    return _TEMPLATES.signals.get((language, metric))


def ordinal(language: str, n: float) -> str | None:
    """ "first" for 1, and so on, or None where there is no word for `n`."""
    words = _TEMPLATES.ordinals.get(language, ())
    return words[int(n) - 1] if n.is_integer() and 1 <= n <= len(words) else None
