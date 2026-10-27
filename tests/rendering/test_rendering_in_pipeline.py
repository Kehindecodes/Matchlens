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


# Words that carry no information of their own, so a sentence made only of them and the
# headline's words says nothing new.
# fmt: off
_FILLER = frozenset({
    "the", "a", "an", "and", "of", "in", "to", "for", "than", "are", "is", "was", "it", "its",
    "with", "from", "by", "at", "on", "as", "their", "them", "they", "that", "this", "there",
    "have", "has", "had", "been", "be",
})
# fmt: on


def _content(text: str) -> set[str]:
    words = {word.strip(".") for word in re.findall(r"[a-z0-9.']+", text.lower())}
    return words - _FILLER - {""}


def test_every_sentence_adds_something_its_headline_did_not_say(published):
    setup = next(i for i in simulate(1) if isinstance(i, MatchSetup))
    team_words = {word for team in setup.match.teams for word in _content(team.name)}
    player_names = {player.name for player in setup.players}
    for card in published:
        if card.rendition.suppressed:
            continue
        headline = _content(card.rendition.headline or "")
        for said in re.split(r"(?<=[.!?])\s+", card.rendition.body or ""):
            # Naming a team the headline did not is not news: "X are creating better chances
            # than Y" under "X are creating far better chances than earlier" repeats it.
            new = _content(said) - headline - team_words
            assert new, f"{card.rendition.headline} | {said}"
            assert said.rstrip(".") not in player_names, f"a name alone: {said}"
