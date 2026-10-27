"""L3 end to end: the cards seed 1 publishes read as the match, not as its ids."""

import re
from collections import defaultdict

import pytest

from apps import pipeline
from matchlens import lenses
from matchlens.models import Depth
from matchlens.rendering import Card
from matchlens.source import MatchSetup, simulate


@pytest.fixture(scope="module")
def published() -> list[Card]:
    cards: list[Card] = []
    pipeline.run(1, cards.append)
    return cards


def _text(card: Card) -> str:
    return f"{card.rendition.headline} {card.rendition.body}"


def test_cards_name_the_teams_and_never_show_an_id(published):
    setup = next(i for i in simulate(1) if isinstance(i, MatchSetup))
    teams = setup.match.teams
    assert published
    for card in published:
        text = _text(card)
        assert any(t.name in text for t in teams), text
        assert not any(t.team_id in text for t in teams), text


def test_the_casual_cards_carry_no_numbers_and_the_analyst_cards_do(published):
    by_depth = {lens.lens_id: lens.depth for lens in lenses.all_lenses()}
    texts = defaultdict(list)
    for card in published:
        texts[by_depth[card.rendition.lens_id]].append(_text(card))
    assert texts[Depth.CASUAL] and texts[Depth.ANALYST]
    assert not any(re.search(r"\d", t) for t in texts[Depth.CASUAL])
    # Not every analyst card has a figure: a chance with no run and no build-up says only that it
    # was a good one, because a shot's quality is never shown as a number.
    assert any(re.search(r"\d", t) for t in texts[Depth.ANALYST])


def test_the_same_moment_reads_differently_in_each_lens_that_shows_it(published):
    by_moment = defaultdict(list)
    for card in published:
        by_moment[card.rendition.moment_id].append(_text(card))
    shared = [texts for texts in by_moment.values() if len(texts) > 1]
    assert shared
    assert all(len(set(texts)) == len(texts) for texts in shared)
