"""L4: three panels, one session per lens (Q24: A), fed from the same bus."""

import re
from collections import defaultdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps import pipeline
from matchlens import lenses
from matchlens.delivery.http import WEB_DIR, create_app
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.rendering import Card

_WEB = [p for p in Path(WEB_DIR).iterdir() if p.suffix in {".html", ".js"}]


@pytest.fixture(scope="module")
def released() -> dict[str, list[Card]]:
    """Seed 1 through the bus to one session per lens, as the page opens them."""
    sessions, queues = SessionStore(), ReleaseQueues()
    by_lens = {
        lens.lens_id: sessions.create(lens.lens_id, focus_team=lens.focus_team)
        for lens in lenses.all_lenses()
    }
    pipeline.run(1, CardRouter(sessions, queues).receive)
    return {lens_id: queues.release_due(s, 10**9) for lens_id, s in by_lens.items()}


def test_the_page_learns_the_lenses_from_the_registry():
    with TestClient(create_app(MatchStateHub(), SessionStore())) as client:
        r = client.get("/lenses")
    assert r.status_code == 200
    rows = r.json()
    assert [row["lens_id"] for row in rows] == [lens.lens_id for lens in lenses.all_lenses()]
    assert all(row["name"] and row["audience"] for row in rows)


def test_the_page_names_no_lens(released):
    # Invariant 10: adding a lens is inserting a row, so the page cannot know any by name.
    for path in _WEB:
        text = path.read_text()
        for lens in lenses.all_lenses():
            assert lens.lens_id not in text, path.name


def test_the_page_has_no_loading_state():
    # An idle panel is choosing not to speak; a spinner or skeleton says it is still loading.
    for path in _WEB:
        assert not re.search(r"\b(spinner|skeleton|loading)\b", path.read_text(), re.I), path.name


def test_each_session_is_released_only_its_own_lens(released):
    for lens_id, cards in released.items():
        assert cards
        assert {c.rendition.lens_id for c in cards} == {lens_id}


def test_no_suppressed_rendition_reaches_a_panel(released):
    assert not any(c.rendition.suppressed for cards in released.values() for c in cards)


def test_each_panel_is_released_in_clock_order(released):
    for cards in released.values():
        clocks = [c.display_at_clock for c in cards]
        assert clocks == sorted(clocks)


def test_the_three_panels_diverge_on_the_demo_match(released):
    counts = {lens_id: len(cards) for lens_id, cards in released.items()}
    assert len(set(counts.values())) == len(counts), counts

    at_clock: dict[int, dict[str, str]] = defaultdict(dict)
    for lens_id, cards in released.items():
        for c in cards:
            at_clock[c.display_at_clock][lens_id] = c.rendition.headline + c.rendition.body
    # The demo shot: one panel fires while another, on the same clock, stays silent.
    assert any(0 < len(texts) < len(released) for texts in at_clock.values())
    # And where two speak at the same clock, they do not say the same thing.
    shared = [texts for texts in at_clock.values() if len(texts) > 1]
    assert shared
    assert all(len(set(t.values())) == len(t) for t in shared)
