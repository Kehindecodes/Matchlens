"""Wording that repeats itself is a defect: the rows must vary and must not restate themselves.

These read the committed template rows, so they run in milliseconds and catch the two ways the
cards went robotic: a body that says what its headline said, and a name said twice in a line.
"""

import json
from collections import Counter

import pytest

from matchlens.rendering import templates
from matchlens.rendering.templates import TEMPLATES_PATH

DATA = json.loads(TEMPLATES_PATH.read_text())


def _headline_variants():
    for row in DATA["headlines"]:
        for spoken in (row, *row.get("variants", ())):
            yield row, spoken


def _fact_variants():
    for row in DATA["facts"]:
        for text in (row["text"], *row.get("variants", ())):
            yield row, text


@pytest.mark.parametrize(
    ("row", "spoken"), list(_headline_variants()), ids=lambda value: str(value)[:60]
)
def test_a_body_never_repeats_its_headline(row, spoken):
    assert spoken["body"].lower() != spoken["headline"].lower()
    assert spoken["headline"].lower().rstrip("!") not in spoken["body"].lower()


@pytest.mark.parametrize(
    ("row", "spoken"), list(_headline_variants()), ids=lambda value: str(value)[:60]
)
def test_a_card_does_not_name_a_team_twice_in_its_body(row, spoken):
    counts = Counter(templates.fields(spoken["body"]))
    assert all(count == 1 for count in counts.values()), spoken
    body_names = templates.fields(spoken["body"]) & {"team", "focus"}
    assert len(body_names) <= 2


@pytest.mark.parametrize(("row", "text"), list(_fact_variants()), ids=lambda value: str(value)[:60])
def test_a_fact_says_no_field_twice(row, text):
    placeholders = [name for _, name, _, _ in templates.Formatter().parse(text) if name]
    assert len(placeholders) == len(set(placeholders)), text


def test_every_headline_row_has_a_variant_that_says_something_else():
    for row in DATA["headlines"]:
        variants = [row, *row.get("variants", ())]
        assert len(variants) >= 2, row
        assert len({(v["headline"], v["body"]) for v in variants}) == len(variants), row


def test_the_variant_a_card_gets_is_stable_and_spreads():
    assert templates.variant_for("moment-e41") == templates.variant_for("moment-e41")
    picks = {templates.variant_for(f"moment-e{n}") % 3 for n in range(40)}
    assert picks == {0, 1, 2}, "forty moments should reach every one of three variants"


def test_lookup_wraps_the_pick_and_variants_differ():
    from matchlens.models import Depth, MomentType

    first = templates.lookup("en", MomentType.CHANCE, Depth.ENGAGED, None, 0)
    second = templates.lookup("en", MomentType.CHANCE, Depth.ENGAGED, None, 1)
    assert first != second
    count = len(templates._TEMPLATES.headlines[("en", MomentType.CHANCE, Depth.ENGAGED, None)])
    assert templates.lookup("en", MomentType.CHANCE, Depth.ENGAGED, None, count) == first
