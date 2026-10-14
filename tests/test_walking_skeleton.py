"""S4: the skeleton walks. One hardcoded moment from a seed to a viewer session, via every stage.

The contract for the wiring (Kehinde writes `apps/pipeline.py`):

    run(seed: int, publish: Callable[[Card], None]) -> None

runs the seeded match through the pipeline stages in order and hands each `Card` to `publish`,
which stands in for Service Bus. Delivery's side of the bus is `CardRouter.receive`.

They are expected to fail until `apps/pipeline.py` exists and the `Claim` schema lands
(Explanation and Verification need content to pass along). The marker is strict, so they turn
into failures the moment they pass: then remove it.
"""

import functools
import importlib

import pytest

from matchlens import calltrace
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.rendering import SKELETON_BODY, SKELETON_HEADLINE
from matchlens.spotting import SKELETON_CLOCK_MS

FOURTEEN = {
    "Match Source", "Ingest", "Understanding", "Spotting", "Explanation", "Verification",
    "Selection", "Rendering", "Catch-up", "Delivery", "Session Clock", "Lens Registry",
    "Control", "Audit",
}  # fmt: skip
EDITORIAL_PATH = ["Spotting", "Explanation", "Verification", "Selection", "Rendering", "Delivery"]


def _pipeline():
    try:
        return importlib.import_module("apps.pipeline")
    except ModuleNotFoundError:
        pytest.fail("apps/pipeline.py does not exist yet: it is Kehinde's to wire (S4)")


pytestmark = pytest.mark.xfail(
    strict=True, reason="S4: waits for apps/pipeline.py (Kehinde) and the Claim schema"
)


@functools.cache
def _walk():
    """Run seed 1 end to end once, recording every component entered."""
    pipeline = _pipeline()
    sessions = SessionStore()
    queues = ReleaseQueues()
    router = CardRouter(sessions, queues)
    session = sessions.create()
    with calltrace.recording() as entered:
        pipeline.run(1, router.receive)
        released = queues.release_due(session, SKELETON_CLOCK_MS)
    return session, released, entered


@pytest.fixture
def walked():
    return _walk()  # cached: the match runs once for all four tests


def _without_repeats(names: list[str]) -> list[str]:
    return [n for i, n in enumerate(names) if i == 0 or names[i - 1] != n]


def test_a_seeded_match_delivers_the_card_to_a_session(walked):
    session, released, _ = walked
    [card] = released
    assert card.rendition.lens_id == session.lens_id
    assert (card.rendition.headline, card.rendition.body) == (SKELETON_HEADLINE, SKELETON_BODY)
    assert not card.rendition.suppressed


def test_the_card_is_at_the_hardcoded_match_clock(walked):
    _, [card], _ = walked
    assert SKELETON_CLOCK_MS <= card.display_at_clock < SKELETON_CLOCK_MS + 10_000


def test_all_fourteen_components_are_entered(walked):
    *_, entered = walked
    assert set(entered) == FOURTEEN, f"never entered: {sorted(FOURTEEN - set(entered))}"


def test_nothing_is_bypassed_between_spotting_and_delivery(walked):
    *_, entered = walked
    path = _without_repeats(entered)
    assert "Explanation" in path, "the moment never reached Explanation"
    first_explanation = path.index("Explanation")
    fired = max(i for i in range(first_explanation) if path[i] == "Spotting")
    hop = path[fired : path.index("Delivery", fired) + 1]
    steps = iter(hop)
    assert all(stage in steps for stage in EDITORIAL_PATH), f"bypassed a stage: {hop}"
