"""S4: the skeleton walks. One hardcoded moment from a seed to a viewer session, via every stage.

`apps.pipeline.run(seed, publish)` runs the seeded match through the pipeline stages and hands
each `Card` to `publish`, which stands in for Service Bus. Delivery's end is `CardRouter.receive`.
Every component logs itself to `matchlens.calltrace` when entered, which the call-path tests read.
"""

import pytest

from apps import pipeline
from matchlens import calltrace
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.rendering import SKELETON_BODY, SKELETON_HEADLINE, Card
from matchlens.spotting import SKELETON_CLOCK_MS

FOURTEEN = {
    "Match Source", "Ingest", "Understanding", "Spotting", "Explanation", "Verification",
    "Selection", "Rendering", "Catch-up", "Delivery", "Session Clock", "Lens Registry",
    "Control", "Audit",
}  # fmt: skip
EDITORIAL_PATH = ["Spotting", "Explanation", "Verification", "Selection", "Rendering", "Delivery"]

# Verification is only entered for a claim, and Explanation returns none until the Claim schema
# lands. Strict, so these turn into failures the moment they pass: then remove the marker.
_WAITS_FOR_A_CLAIM = pytest.mark.xfail(
    strict=True, reason="Verification is never entered until Explanation returns a claim"
)


@pytest.fixture(scope="module")
def walked():
    """Seed 1 end to end on the default lens, recording every component entered."""
    sessions, queues = SessionStore(), ReleaseQueues()
    session = sessions.create()
    with calltrace.recording() as entered:
        pipeline.run(1, CardRouter(sessions, queues).receive)
        released = queues.release_due(session, SKELETON_CLOCK_MS)
    return session, released, entered


def _without_repeats(names: list[str]) -> list[str]:
    return [n for i, n in enumerate(names) if i == 0 or names[i - 1] != n]


def test_a_seeded_match_delivers_the_card_to_a_session(walked):
    session, released, _ = walked
    [card] = released
    assert isinstance(card, Card)
    assert card.rendition.lens_id == session.lens_id
    assert (card.rendition.headline, card.rendition.body) == (SKELETON_HEADLINE, SKELETON_BODY)
    assert not card.rendition.suppressed


def test_the_card_is_at_the_hardcoded_match_clock(walked):
    _, [card], _ = walked
    assert SKELETON_CLOCK_MS <= card.display_at_clock < SKELETON_CLOCK_MS + 10_000


@_WAITS_FOR_A_CLAIM
def test_all_fourteen_components_are_entered(walked):
    *_, entered = walked
    assert set(entered) == FOURTEEN, f"never entered: {sorted(FOURTEEN - set(entered))}"


@_WAITS_FOR_A_CLAIM
def test_nothing_is_bypassed_between_spotting_and_delivery(walked):
    *_, entered = walked
    path = _without_repeats(entered)
    assert "Explanation" in path, "the moment never reached Explanation"
    first_explanation = path.index("Explanation")
    fired = max(i for i in range(first_explanation) if path[i] == "Spotting")
    hop = path[fired : path.index("Delivery", fired) + 1]
    steps = iter(hop)
    assert all(stage in steps for stage in EDITORIAL_PATH), f"bypassed a stage: {hop}"
