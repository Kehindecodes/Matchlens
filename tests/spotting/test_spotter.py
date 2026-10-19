import pytest

from matchlens.models import Event, Frame, RefKind
from matchlens.spotting import SKELETON_CLOCK_MS, Spotter
from tests.source.helpers import Played


@pytest.fixture(scope="module")
def match_1() -> Played:
    from matchlens.source import simulate
    from tests.source.helpers import split

    return split(list(simulate(1)))


def _fired(match: Played):
    spotter = Spotter()
    return [r.moment for item in match.items[1:] if (r := spotter.consider((), item)) is not None]  # type: ignore[arg-type]


def test_the_stub_fires_exactly_once(match_1: Played):
    assert len(_fired(match_1)) == 1


def test_it_fires_on_the_first_team_event_at_or_after_67_12(match_1: Played):
    [moment] = _fired(match_1)
    first = next(
        e for e in match_1.events if e.clock_ms >= SKELETON_CLOCK_MS and e.team is not None
    )
    assert moment.clock_ms == first.clock_ms
    assert moment.trigger_event_ids == (first.event_id,)
    assert moment.subject.kind is RefKind.TEAM and moment.subject.id == first.team


def test_it_never_fires_on_a_frame(match_1: Played):
    spotter = Spotter()
    late_frames = [f for f in match_1.frames if f.clock_ms >= SKELETON_CLOCK_MS]
    assert all(spotter.consider((), f) is None for f in late_frames)
    assert not any(isinstance(f, Event) for f in late_frames) and all(
        isinstance(f, Frame) for f in late_frames
    )
