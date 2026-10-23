"""The template rows Rendering fills, read from committed data.

Rows are keyed on language, moment type and depth, never on a lens, so a lens is free to change
without a template changing (invariant 10). A fact row is keyed on the metric of the claim it
phrases; a claim whose metric has no row is not spoken, because a number nobody templated is a
number nobody agreed to say. The metric vocabulary is not settled (Q23), so the rows hold only
the metric that exists.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from string import Formatter

from matchlens.models import Depth, MomentType

TEMPLATES_PATH = Path(__file__).with_name("templates.json")

_HEADLINE_FIELDS = frozenset({"team", "window"})
_FACT_FIELDS = frozenset({"value"})


@dataclass(frozen=True)
class Words:
    headline: str
    body: str


def _fields(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


def _checked(template: str, allowed: frozenset[str]) -> str:
    unknown = _fields(template) - allowed
    if unknown:
        raise ValueError(
            f"template {template!r} uses {sorted(unknown)}, which Rendering never fills"
        )
    return template


def load(
    path: Path = TEMPLATES_PATH,
) -> tuple[dict[tuple[str, MomentType, Depth], Words], dict[tuple[str, str], str]]:
    """The headline rows and the fact rows in this file, each checked for the fields it uses."""
    data = json.loads(path.read_text())
    headlines = {
        (row["language"], MomentType(row["moment_type"]), Depth(row["depth"])): Words(
            _checked(row["headline"], _HEADLINE_FIELDS), _checked(row["body"], _HEADLINE_FIELDS)
        )
        for row in data["headlines"]
    }
    facts = {
        (row["language"], row["metric"]): _checked(row["text"], _FACT_FIELDS)
        for row in data["facts"]
    }
    return headlines, facts


_HEADLINES, _FACTS = load()


def lookup(language: str, type_: MomentType, depth: Depth) -> Words:
    """The words for this moment type at this depth. Raises `LookupError` if there are none."""
    try:
        return _HEADLINES[(language, type_, depth)]
    except KeyError:
        raise LookupError(f"no template for {type_} at {depth} in {language!r}") from None


def fact(language: str, metric: str) -> str | None:
    """How to phrase a claim measuring `metric`, or None if nobody has said how."""
    return _FACTS.get((language, metric))
