"""F4 acceptance criteria for the replay harness.

Every test runs against a fake clock whose `sleep` just advances it, so a 95-minute match at 1x
takes milliseconds. The replay never reads wall time itself; it is handed `now` and `sleep`.
"""

import pytest

from matchlens.models import Event, Frame
from matchlens.source.replay import FAST_SPEED, Replay, main
from matchlens.source.stream import MatchSetup
from tests.source.helpers import Played

MIN = 60_000
STREAM = (Frame, Event)


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0
        self.t += seconds


def replay_of(played: Played, clock: FakeClock, **kwargs) -> Replay:
    return Replay(played.items, now=clock.now, sleep=clock.sleep, **kwargs)


def run_to_the_end(played: Played, speed: float) -> tuple[list, list[float]]:
    """Every stream item with the fake time it was emitted at."""
    clock = FakeClock()
    items, times = [], []
    for item in replay_of(played, clock, speed=speed):
        if isinstance(item, MatchSetup):
            continue
        items.append(item)
        times.append(clock.now())
    return items, times


# --- order -------------------------------------------------------------------------------------


@pytest.mark.parametrize("speed", [1, 5, FAST_SPEED])
def test_seq_is_monotonic_and_nothing_is_dropped_at_every_speed(match_1, speed):
    items, _ = run_to_the_end(match_1, speed)
    seqs = [i.seq for i in items]
    assert seqs == sorted(seqs)
    assert seqs == [i.seq for i in match_1.items[1:]]


def test_the_roster_comes_first_and_only_once(match_1):
    clock = FakeClock()
    r = replay_of(match_1, clock, speed=1000)
    out = list(r)
    assert isinstance(out[0], MatchSetup)
    assert not any(isinstance(i, MatchSetup) for i in out[1:])


# --- relative timing ---------------------------------------------------------------------------


@pytest.mark.parametrize("speed", [1, 5, FAST_SPEED])
def test_gaps_between_items_scale_with_the_speed_multiplier(match_1, speed):
    items, times = run_to_the_end(match_1, speed)
    for item, t in zip(items, times, strict=True):
        wall_gap = t - times[0]
        match_gap = (item.clock_ms - items[0].clock_ms) / 1000
        assert wall_gap * speed == pytest.approx(match_gap, abs=0.01)


@pytest.mark.parametrize("played", ["match_1", "match_2"])
def test_a_full_match_replays_in_under_four_minutes_at_the_fast_speed(played, request):
    # F4 criterion, settled as 25x in Q3. Also story J1 (a full match in under five minutes).
    _, times = run_to_the_end(request.getfixturevalue(played), FAST_SPEED)
    assert times[-1] < 4 * 60


def test_speed_can_change_while_playing(match_1):
    clock = FakeClock()
    r = replay_of(match_1, clock, speed=1)
    r.play()
    clock.t += 10
    assert r.position_ms == pytest.approx(10_000)
    r.set_speed(20)
    clock.t += 1
    assert r.position_ms == pytest.approx(30_000)


@pytest.mark.parametrize("bad", [0, -1, -0.5])
def test_speed_must_be_positive(match_1, bad):
    with pytest.raises(ValueError):
        replay_of(match_1, FakeClock(), speed=bad)
    r = replay_of(match_1, FakeClock())
    with pytest.raises(ValueError):
        r.set_speed(bad)


# --- pause -------------------------------------------------------------------------------------


def test_pause_stops_emission_and_resume_continues_without_gaps_or_repeats(match_1):
    clock = FakeClock()
    r = replay_of(match_1, clock, speed=5)
    r.play()
    clock.t += 60  # 300 s of match
    first = r.poll()
    assert first
    position = r.position_ms
    r.pause()
    clock.t += 600
    assert r.poll() == []
    assert r.position_ms == position
    r.play()
    clock.t += 10_000
    rest = r.poll()
    assert [i.seq for i in first + rest] == [i.seq for i in match_1.items[1:]]
    assert r.finished


def test_pausing_inside_the_stream_shifts_everything_after_it_by_the_pause(match_1):
    clock = FakeClock()
    pause_at, resume_at = 100.0, 160.0
    paused_position: list[float] = []

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        if pause_at <= clock.now() < resume_at and r.playing:
            paused_position.append(r.position_ms)
            r.pause()
        elif clock.now() >= resume_at and not r.playing:
            r.play()

    r = Replay(match_1.items, now=clock.now, sleep=sleep)
    emitted = [(clock.now(), i) for i in r if not isinstance(i, MatchSetup)]

    assert [i.seq for _, i in emitted] == [i.seq for i in match_1.items[1:]]
    assert len(paused_position) == 1
    for t, item in emitted:
        assert not (pause_at + 0.2 < t < resume_at)  # nothing while paused
        if item.clock_ms > paused_position[0] + 1000:  # everything after is shifted by the pause
            assert t == pytest.approx(item.clock_ms / 1000 + (resume_at - pause_at), abs=0.2)


# --- seek --------------------------------------------------------------------------------------


def test_seeking_forward_emits_from_that_clock_with_nothing_before_it(match_1):
    clock = FakeClock()
    r = replay_of(match_1, clock)
    r.seek(30 * MIN)
    r.play()
    clock.t += 1
    out = r.poll()
    assert out
    assert all(i.clock_ms >= 30 * MIN for i in out)
    expected_first = next(i for i in match_1.items[1:] if i.clock_ms >= 30 * MIN)
    assert out[0].seq == expected_first.seq


def test_seeking_backwards_re_yields_from_that_point(match_1):
    clock = FakeClock()
    r = replay_of(match_1, clock, speed=20)
    r.play()
    clock.t += 60  # 20 minutes of match
    seen = r.poll()
    assert seen[-1].clock_ms > 15 * MIN

    r.seek(10 * MIN)
    at_the_seek = r.poll()
    assert all(i.clock_ms == 10 * MIN for i in at_the_seek)  # only what is stamped exactly there
    clock.t += 1
    again = at_the_seek + r.poll()
    assert again
    assert all(i.clock_ms >= 10 * MIN for i in again)
    assert again[0].seq < seen[-1].seq  # it went back, and re-yielded
    assert again[0].seq == next(i for i in match_1.items[1:] if i.clock_ms >= 10 * MIN).seq


def test_seek_does_not_resend_the_roster(match_1):
    clock = FakeClock()
    r = replay_of(match_1, clock, speed=1000)
    out = []
    for item in r:
        out.append(item)
        if len(out) == 50:
            r.seek(0)
        if len(out) > 400:
            break
    assert sum(isinstance(i, MatchSetup) for i in out) == 1


def test_seeking_past_the_end_finishes_the_replay(match_1):
    clock = FakeClock()
    r = replay_of(match_1, clock)
    r.seek(10_000 * MIN)
    r.play()
    clock.t += 1
    assert r.poll() == []
    assert r.finished


def test_seeking_to_a_negative_clock_is_rejected(match_1):
    with pytest.raises(ValueError):
        replay_of(match_1, FakeClock()).seek(-1)


# --- input checks ------------------------------------------------------------------------------


def test_the_stream_must_start_with_the_roster(match_1):
    with pytest.raises(ValueError):
        Replay(match_1.items[1:], now=FakeClock().now, sleep=FakeClock().sleep)


def test_the_stream_must_be_in_seq_order(match_1):
    items = match_1.items
    with pytest.raises(ValueError):
        Replay([items[0], items[2], items[1]], now=FakeClock().now, sleep=FakeClock().sleep)


def test_from_seed_builds_the_same_stream_as_the_simulator():
    clock = FakeClock()
    r = Replay.from_seed(1, frame_rate_hz=1, now=clock.now, sleep=clock.sleep, speed=1000)
    out = list(r)
    assert isinstance(out[0], MatchSetup)
    assert out[0].match.seed == 1
    assert [i.seq for i in out[1:]] == list(range(len(out) - 1))


# --- the CLI -----------------------------------------------------------------------------------


def test_cli_replays_a_seed_and_prints_the_goals(capsys):
    code = main(["--seed", "1", "--speed", "1000000", "--hz", "1", "--key-only"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.count("GOAL") == 3
    assert out.count("Added time announced") == 2  # one per half
    assert "Full time" in out
