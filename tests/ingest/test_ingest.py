"""S2: Ingest accepts the stream, bounds the frame window and persists events.

`test_agents_cannot_reach_frames` is Kehinde's (S2 is 🤝).
"""

import pytest

from matchlens.config.settings import settings
from matchlens.ingest import Ingest, InMemoryEventRepository, RosterNotLoaded
from matchlens.ingest.frames import FrameAccess, FrameWindow
from matchlens.ingest.record import RecordReader
from matchlens.models import Event, Frame, Phase
from tests.source.helpers import Played

MIN = 60_000


def _loaded(match: Played) -> Ingest:
    ingest = Ingest()
    for item in match.items:
        ingest.accept(item)
    return ingest


@pytest.fixture(scope="module")
def ingested(match_1: Played) -> Ingest:
    return _loaded(match_1)


def _frame(seq: int, clock_ms: int) -> Frame:
    return Frame(
        seq=seq, clock_ms=clock_ms, period=1, phase=Phase.IN_PLAY, ball_x=0.0, ball_y=0.0,
        ball_z=0.0, ball_speed=0.0, carrier=None, players=(),
    )  # fmt: skip


# --- the roster comes first (D16) -----------------------------------------------------------------


def test_an_event_before_the_roster_is_refused(match_1: Played):
    with pytest.raises(RosterNotLoaded):
        Ingest().accept(match_1.events[0])


def test_a_frame_before_the_roster_is_refused(match_1: Played):
    with pytest.raises(RosterNotLoaded):
        Ingest().accept(match_1.frames[0])


def test_there_is_no_record_before_the_roster():
    with pytest.raises(RosterNotLoaded):
        Ingest().record()


def test_the_roster_loads_once(match_1: Played):
    ingest = Ingest()
    ingest.accept(match_1.setup)
    with pytest.raises(ValueError, match="once"):
        ingest.accept(match_1.setup)


def test_an_event_naming_an_unknown_player_is_refused(match_1: Played):
    ingest = Ingest()
    ingest.accept(match_1.setup)
    event = next(e for e in match_1.events if e.player is not None)
    with pytest.raises(ValueError, match="unknown player"):
        ingest.accept(event.model_copy(update={"player": "nobody"}))


# --- seq order ---------------------------------------------------------------------------------


def test_a_whole_match_is_accepted_in_seq_order(match_1: Played, ingested: Ingest):
    record = ingested.record()
    assert record.events_between(0, match_1.end_clock_ms + 1) == tuple(match_1.events)
    assert record.match == match_1.setup.match
    assert record.players == match_1.setup.players


def test_an_item_out_of_seq_order_is_refused(match_1: Played):
    ingest = Ingest()
    ingest.accept(match_1.setup)
    first, second = match_1.items[1], match_1.items[2]
    ingest.accept(second)
    with pytest.raises(ValueError, match="seq"):
        ingest.accept(first)


def test_a_repeated_item_is_refused(match_1: Played):
    ingest = Ingest()
    ingest.accept(match_1.setup)
    ingest.accept(match_1.items[1])
    with pytest.raises(ValueError, match="seq"):
        ingest.accept(match_1.items[1])


# --- the frame window -----------------------------------------------------------------------------


def test_frame_window_returns_only_frames_inside_the_span(match_1: Played):
    ingest = Ingest()
    frames = ingest.frame_access()
    clock, span = 20 * MIN, 2 * MIN
    for item in match_1.items:
        if not isinstance(item, Frame | Event) or item.clock_ms <= clock:
            ingest.accept(item)
    got = frames.frame_window(clock, span)
    expected = [f for f in match_1.frames if clock - span < f.clock_ms <= clock]
    assert got == expected
    assert got  # the span is not empty at 20:00


def test_the_window_is_bounded_over_a_full_match(match_1: Played):
    retention = settings.signal_window_ms
    ingest = Ingest(frame_retention_ms=retention)
    window = ingest._window  # the bound is a property of the private store
    cap = retention * settings.frame_rate_hz // 1000 + 1
    peak = 0
    for item in match_1.items:
        ingest.accept(item)
        peak = max(peak, len(window))
    assert len(match_1.frames) > 10 * cap  # a full match is far larger than the window
    assert peak <= cap


def test_the_window_holds_the_most_recent_retention():
    window = FrameWindow(retention_ms=1_000)
    for seq, clock in enumerate([0, 500, 1_000, 1_500, 2_000]):
        window.append(_frame(seq, clock))
    assert [f.clock_ms for f in window.between(2_000, 1_000)] == [1_500, 2_000]
    assert len(window) == 2


def test_a_span_beyond_the_retention_is_refused():
    window = FrameWindow(retention_ms=1_000)
    with pytest.raises(ValueError, match="span_ms"):
        window.between(5_000, 1_001)


# --- events by clock range ------------------------------------------------------------------------


def test_events_are_retrievable_by_clock_range(match_1: Played, ingested: Ingest):
    lo, hi = 10 * MIN, 15 * MIN
    got = ingested.record().events_between(lo, hi)
    assert got == tuple(e for e in match_1.events if lo <= e.clock_ms < hi)
    assert got


def test_a_range_is_a_snapshot(match_1: Played):
    ingest = Ingest()
    ingest.accept(match_1.setup)
    events = iter(match_1.events)
    ingest.accept(next(events))
    before = ingest.record().events_between(0, 10**9)
    ingest.accept(next(events))
    assert len(before) == 1


def test_the_event_log_is_append_only(match_1: Played):
    repo = InMemoryEventRepository()
    repo.append(match_1.events[0])
    with pytest.raises(ValueError, match="append-only"):
        repo.append(match_1.events[0])
    assert not hasattr(repo, "update")
    assert not hasattr(repo, "delete")


def test_ingest_writes_to_the_repository_it_is_given(match_1: Played):
    repo = InMemoryEventRepository()
    ingest = Ingest(repo)
    for item in match_1.items[:200]:
        ingest.accept(item)
    assert len(repo) == sum(isinstance(i, Event) for i in match_1.items[:200])


def test_agents_cannot_reach_frames(match_1: Played):
    ingest = Ingest()
    ingest.accept(item=match_1.setup)
    record_reader: RecordReader = ingest.record()
    frames_types = (Frame, FrameWindow, FrameAccess, Ingest)
    has_match: bool = any(isinstance(value, frames_types) for value in vars(record_reader).values())
    assert not has_match
