"""M2: cooldown and duplicate detection, on constructed sequences of readings.

Each test hands a spotter one reading a minute, as the live path does, and asks which minutes
produced a moment. A generated match is not used to prove a rule: it may not contain the case.
"""

import pytest

from matchlens.config import settings
from matchlens.ingest import Ingest
from matchlens.models import Action, MomentType, Outcome, Signal, SignalReading, Trend
from matchlens.spotting import Spotter
from matchlens.understanding import Understanding
from tests.source.helpers import played

MINUTE = 60_000
COOLDOWN_MIN = settings.spotter_cooldown_ms // MINUTE
OVER = 1.5  # over the threshold
BETWEEN = 1.1  # under the threshold, over the release: still the same shift
GONE = 0.2  # back to ordinary


@pytest.fixture(scope="module")
def wiring():
    """A real log and understanding to build spotters on, a quiet event and a goal to hand them."""
    match = played("comeback", 1)
    ingest = Ingest()
    understanding = Understanding(ingest.record)
    for item in match.items[:200]:
        ingest.accept(item)
        understanding.observe(item)
    quiet = next(e for e in match.events if e.action is Action.PASS and e.clock_ms > MINUTE)
    goal = next(e for e in match.events if e.outcome is Outcome.GOAL)

    def fresh() -> Spotter:
        return Spotter(ingest.record, understanding.epoch_at)

    return fresh, quiet, goal


def _reading(
    minute: int,
    z_match: float,
    signal: Signal = Signal.PRESSING_INTENSITY,
    team: str = "home",
    window_ms: int = 300_000,
) -> SignalReading:
    return SignalReading(
        reading_id=f"m-epoch0-{signal}-{team}-{minute * MINUTE}",
        signal=signal,
        team=team,
        clock_ms=minute * MINUTE,
        window_ms=window_ms,
        value=1.0,
        baseline=0.5,
        z_match=z_match,
        z_prior=0.0,
        trend=Trend.STEADY,
        confidence=0.9,
        epoch_id="m-epoch0",
    )


def _fired_minutes(wiring, series: dict[int, float], **kwargs) -> list[int]:
    """The minutes at which one series, given as {minute: z_match}, produced a moment."""
    fresh, quiet, _ = wiring
    spotter = fresh()
    fired = []
    for minute, z in sorted(series.items()):
        results = spotter.consider([_reading(minute, z, **kwargs)], quiet)
        if results:
            fired.append(minute)
    return fired


# --- cooldown ----------------------------------------------------------------------------------


def test_the_same_series_cannot_fire_twice_inside_the_cooldown(wiring):
    # Gone between the two, so duplicate detection is not what stops the second one.
    series = {38: OVER, 39: GONE, 40: OVER}
    assert _fired_minutes(wiring, series) == [38]


def test_the_cooldown_ends_exactly_one_window_after_the_moment(wiring):
    last_blocked, first_allowed = 38 + COOLDOWN_MIN - 1, 38 + COOLDOWN_MIN
    assert _fired_minutes(wiring, {38: OVER, last_blocked - 1: GONE, last_blocked: OVER}) == [38]
    assert _fired_minutes(wiring, {38: OVER, first_allowed - 1: GONE, first_allowed: OVER}) == [
        38,
        first_allowed,
    ]


def test_a_new_shift_after_the_cooldown_fires(wiring):
    series = {38: OVER, 39: GONE, 55: OVER}
    assert _fired_minutes(wiring, series) == [38, 55]


def test_a_blocked_shift_does_not_restart_the_cooldown(wiring):
    # 40 is blocked. If it had restarted the clock, 42 would be blocked too.
    series = {38: OVER, 39: GONE, 40: OVER, 41: GONE, 38 + COOLDOWN_MIN: OVER}
    assert _fired_minutes(wiring, series) == [38, 38 + COOLDOWN_MIN]


def test_the_cooldown_is_per_signal_and_team(wiring):
    fresh, quiet, _ = wiring
    spotter = fresh()
    first = spotter.consider([_reading(38, OVER)], quiet)
    others = [
        _reading(39, OVER, team="away"),
        _reading(39, OVER, signal=Signal.TERRITORY),
        _reading(39, OVER, signal=Signal.TERRITORY, team="away"),
    ]
    assert len(first) == 1
    assert len(spotter.consider(others, quiet)) == 3


def test_a_reversal_inside_the_cooldown_is_blocked_and_outside_it_fires(wiring):
    assert _fired_minutes(wiring, {38: OVER, 40: -OVER}) == [38]
    assert _fired_minutes(wiring, {38: OVER, 38 + COOLDOWN_MIN: -OVER}) == [38, 38 + COOLDOWN_MIN]


def test_the_cooldown_window_is_a_setting(wiring, monkeypatch):
    series = {38: OVER, 39: GONE, 40: OVER}
    assert _fired_minutes(wiring, series) == [38]
    monkeypatch.setattr(settings, "spotter_cooldown_ms", MINUTE)
    assert _fired_minutes(wiring, series) == [38, 40]


# --- duplicate detection -----------------------------------------------------------------------


def test_a_series_hovering_at_the_threshold_fires_once(wiring):
    # Never drops to the release level, so it never leaves the shift: one event, not five.
    series = {38: OVER, 39: BETWEEN, 40: OVER, 41: BETWEEN, 42: OVER, 43: BETWEEN, 44: OVER}
    assert _fired_minutes(wiring, series) == [38]


def test_hovering_is_still_one_event_once_the_cooldown_has_run_out(wiring):
    # Duplicate detection is about state, not time: 14 minutes later it is still the same shift.
    series = {38: OVER, **{m: BETWEEN if m % 2 else OVER for m in range(39, 52)}}
    assert _fired_minutes(wiring, series) == [38]


def test_a_series_oscillating_across_the_range_fires_once_per_cooldown(wiring):
    inside_one_window = {m: OVER if m % 2 == 0 else GONE for m in range(38, 38 + COOLDOWN_MIN)}
    assert _fired_minutes(wiring, inside_one_window) == [38]

    long_run = {m: OVER if m % 2 == 0 else GONE for m in range(38, 60)}
    fired = _fired_minutes(wiring, long_run)
    assert len(fired) > 1
    assert all(
        later - earlier >= COOLDOWN_MIN for earlier, later in zip(fired, fired[1:], strict=False)
    )


def test_a_reading_that_stays_over_the_threshold_fires_once(wiring):
    assert _fired_minutes(wiring, dict.fromkeys(range(38, 48), OVER)) == [38]


def test_a_thin_window_ends_the_shift_so_the_baseline_reset_can_start_a_new_one(wiring):
    # Over at 38, then a thin reading (a break just happened), then over again once it is long.
    fresh, quiet, _ = wiring
    spotter = fresh()
    assert len(spotter.consider([_reading(38, OVER)], quiet)) == 1
    assert spotter.consider([_reading(39, OVER, window_ms=60_000)], quiet) == []
    later = 38 + COOLDOWN_MIN
    assert len(spotter.consider([_reading(later, OVER)], quiet)) == 1


# --- goals and state ---------------------------------------------------------------------------


def test_a_goal_fires_inside_an_active_cooldown(wiring):
    fresh, quiet, goal = wiring
    spotter = fresh()
    [shift] = spotter.consider([_reading(goal.clock_ms // MINUTE - 1, OVER)], quiet)
    goals = spotter.consider([], goal)
    assert shift.moment.type is MomentType.TACTICAL_SHIFT
    assert [r.moment.type for r in goals] == [MomentType.GOAL]


def test_goals_in_quick_succession_all_fire(wiring):
    fresh, _, goal = wiring
    spotter = fresh()
    again = goal.model_copy(update={"event_id": "again", "clock_ms": goal.clock_ms + 30_000})
    assert len(spotter.consider([], goal)) == 1
    assert len(spotter.consider([], again)) == 1


def test_two_spotters_share_no_suppression_state(wiring):
    fresh, quiet, _ = wiring
    one, other = fresh(), fresh()
    assert len(one.consider([_reading(38, OVER)], quiet)) == 1
    assert len(other.consider([_reading(39, OVER)], quiet)) == 1  # inside one's cooldown
