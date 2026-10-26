"""M1b: the spotter, over seed 1 on each of the four archetypes.

A tactical shift fires on `z_match` (Q19), and `z_prior` only raises its importance. Only three
moment types are emitted (Q20). The match tests stream a whole match through Ingest,
Understanding and Spotter as the pipeline does; the constructed ones hand the spotter a single
reading and check the one rule under test.
"""

from dataclasses import dataclass

import pytest

from matchlens import calltrace
from matchlens.config import settings
from matchlens.ingest import Ingest
from matchlens.models import (
    Action,
    Event,
    Frame,
    Moment,
    MomentType,
    Outcome,
    Signal,
    SignalReading,
    Trend,
)
from matchlens.source import MatchSetup
from matchlens.source.archetypes import ARCHETYPES
from matchlens.spotting import Spotter
from matchlens.understanding import Understanding
from matchlens.understanding.epochs import detect
from matchlens.understanding.shot_value import is_shot
from matchlens.understanding.signals import SIGNALS
from tests.source.helpers import Played, played
from tests.source.helpers import reader as match_reader

MINUTE = 60_000


@dataclass(frozen=True)
class Spotted:
    moments: list[Moment]
    readings: list[SignalReading]
    events: list[Event]


def _spot(match: Played) -> Spotted:
    ingest = Ingest()
    understanding = Understanding(ingest.record)
    spotter = Spotter(ingest.record, understanding.epoch_at)
    moments, readings = [], []
    for item in match.items:
        ingest.accept(item)
        if isinstance(item, MatchSetup):
            continue  # the roster is not something to spot, and the pipeline skips it too
        new = understanding.observe(item)
        readings += new
        moments += [r.moment for r in spotter.consider(new, item)]
    return Spotted(moments, readings, match.events)


@pytest.fixture(scope="module", params=sorted(ARCHETYPES))
def spotted(request) -> Spotted:
    return _spot(played(request.param, 1))


# --- constructed: one reading, one rule ---------------------------------------------------------


@pytest.fixture(scope="module")
def started():
    """A spotter wired to a real log, and a quiet event to hand it alongside a reading."""
    match = played("comeback", 1)
    ingest = Ingest()
    understanding = Understanding(ingest.record)
    for item in match.items[:200]:
        ingest.accept(item)
        understanding.observe(item)
    quiet = next(
        e for e in match.events if e.action is Action.PASS and e.clock_ms > MINUTE
    )  # not a goal, not a shot

    def fresh() -> Spotter:
        return Spotter(ingest.record, understanding.epoch_at)

    return fresh, quiet


def _reading(
    signal: Signal = Signal.PRESSING_INTENSITY,
    team: str = "home",
    clock_ms: int = 600_000,
    z_match: float = 3.0,
    z_prior: float = 0.0,
    confidence: float = 0.9,
    window_ms: int = 300_000,
    epoch_id: str = "m-epoch0",
) -> SignalReading:
    return SignalReading(
        reading_id=f"{epoch_id}-{signal}-{team}-{clock_ms}",
        signal=signal,
        team=team,
        clock_ms=clock_ms,
        window_ms=window_ms,
        value=1.0,
        baseline=0.5,
        z_match=z_match,
        z_prior=z_prior,
        trend=Trend.STEADY,
        confidence=confidence,
        epoch_id=epoch_id,
    )


def _fire(started, *readings: SignalReading) -> list[Moment]:
    fresh, quiet = started
    spotter = fresh()
    return [r.moment for r in spotter.consider(list(readings), quiet)]


def test_a_large_z_match_on_a_full_window_fires_a_tactical_shift(started):
    [moment] = _fire(started, _reading())
    assert moment.type is MomentType.TACTICAL_SHIFT
    assert moment.subject.id == "home"


def test_z_prior_alone_does_not_fire(started):
    assert _fire(started, _reading(z_match=0.0, z_prior=5.0)) == []


def test_z_match_fires_in_either_direction(started):
    assert len(_fire(started, _reading(z_match=-3.0))) == 1


def test_a_z_below_the_threshold_is_silent(started):
    below = settings.spotter_z_threshold - 0.01
    assert _fire(started, _reading(z_match=below)) == []


def test_no_moment_fires_below_the_confidence_floor(started):
    floor = settings.spotter_confidence_floor
    assert _fire(started, _reading(z_match=6.0, confidence=floor - 0.01)) == []
    assert len(_fire(started, _reading(z_match=6.0, confidence=floor))) == 1  # the control


def test_a_thin_window_is_silent_however_confident_it_looks(started):
    thin = settings.spotter_min_window_ms - 1
    assert _fire(started, _reading(z_match=6.0, window_ms=thin)) == []


def test_a_series_that_stays_above_the_threshold_fires_once_when_it_crosses(started):
    fresh, quiet = started
    spotter = fresh()
    fired = [
        spotter.consider([_reading(clock_ms=n * MINUTE, z_match=z)], quiet)
        for n, z in enumerate([0.1, 3.0, 3.1, 3.2, 0.2, 3.0], start=10)
    ]
    assert [len(f) for f in fired] == [0, 1, 0, 0, 0, 1]


def test_each_team_and_signal_is_its_own_series(started):
    readings = [
        _reading(team=team, signal=signal)
        for team in ("home", "away")
        for signal in (Signal.CHANCE_QUALITY, Signal.PRESSING_INTENSITY)
    ]
    assert len(_fire(started, *readings)) == 4


def test_a_shift_cites_its_reading_alone(started):
    reading = _reading()
    [moment] = _fire(started, reading)
    assert moment.trigger_reading_ids == (reading.reading_id,)
    assert moment.trigger_event_ids == ()
    assert moment.clock_ms == reading.clock_ms
    assert moment.epoch_id == reading.epoch_id


# --- importance ---------------------------------------------------------------------------------


def _importance(started, **kwargs) -> float:
    [moment] = _fire(started, _reading(**kwargs))
    return moment.importance


def test_importance_does_not_depend_on_which_signal_shifted(started):
    scores = {s: _importance(started, signal=s, z_match=3.0) for s in SIGNALS}
    assert len(set(scores.values())) == 1, scores


def test_importance_rises_with_the_size_of_the_shift(started):
    small, large = (_importance(started, z_match=z) for z in (1.5, 3.0))
    assert small < large


def test_importance_rises_with_confidence(started):
    low, high = (_importance(started, confidence=c) for c in (0.4, 0.9))
    assert low < high


def test_z_prior_raises_importance_but_never_fires(started):
    ordinary = _importance(started, z_prior=0.0)
    unusual = _importance(started, z_prior=3.0)
    assert ordinary < unusual


def test_importance_is_a_unit_interval_however_large_the_z(started):
    assert 0 < _importance(started, z_match=40.0, z_prior=40.0, confidence=1.0) <= 1.0


def test_a_goal_outranks_a_chance_which_outranks_a_typical_shift(spotted):
    best = {
        t: max(m.importance for m in spotted.moments if m.type is t)
        for t in {m.type for m in spotted.moments}
    }
    assert best[MomentType.GOAL] == max(best.values())
    mean_shift = _mean(m.importance for m in spotted.moments if m.type is MomentType.TACTICAL_SHIFT)
    assert mean_shift < best[MomentType.GOAL]


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values)


# --- the match ----------------------------------------------------------------------------------


def test_there_are_between_20_and_60_moments(spotted):
    # The floor was 30 until the mirror rule (M2) stopped telling one possession swing, or one
    # territory swing, as two shifts; the scrappy match, where both flip most, went from 32 to
    # 22 (Q46).
    assert 20 <= len(spotted.moments) <= 60, len(spotted.moments)


def test_only_goals_chances_and_shifts_are_emitted(spotted):
    types = {m.type for m in spotted.moments}
    assert types <= {MomentType.GOAL, MomentType.CHANCE, MomentType.TACTICAL_SHIFT}
    assert MomentType.MILESTONE not in types and MomentType.PATTERN not in types


def test_every_goal_is_a_moment_and_nothing_else_is_called_one(spotted):
    goals = {e.event_id for e in spotted.events if e.outcome is Outcome.GOAL}
    cited = {i for m in spotted.moments if m.type is MomentType.GOAL for i in m.trigger_event_ids}
    assert cited == goals


def test_a_chance_is_a_shot_that_was_not_a_goal(spotted):
    by_id = {e.event_id: e for e in spotted.events}
    chances = [m for m in spotted.moments if m.type is MomentType.CHANCE]
    assert chances, "no chance moments to check"
    for m in chances:
        [event_id] = m.trigger_event_ids
        assert is_shot(by_id[event_id]) and by_id[event_id].outcome is not Outcome.GOAL


def test_every_moment_cites_what_fired_it_and_only_that(spotted):
    reading_ids = {r.reading_id for r in spotted.readings}
    event_ids = {e.event_id for e in spotted.events}
    for m in spotted.moments:
        if m.type is MomentType.TACTICAL_SHIFT:
            assert len(m.trigger_reading_ids) == 1 and m.trigger_event_ids == ()
        else:
            assert len(m.trigger_event_ids) == 1 and m.trigger_reading_ids == ()
        assert set(m.trigger_reading_ids) <= reading_ids
        assert set(m.trigger_event_ids) <= event_ids


def test_a_shift_cites_a_reading_whose_z_match_is_over_the_threshold(spotted):
    by_id = {r.reading_id: r for r in spotted.readings}
    for m in spotted.moments:
        for reading_id in m.trigger_reading_ids:
            reading = by_id[reading_id]
            assert abs(reading.z_match) >= settings.spotter_z_threshold
            assert reading.confidence >= settings.spotter_confidence_floor


def test_no_shift_in_the_opening_minutes(spotted):
    opening = [
        m
        for m in spotted.moments
        if m.type is MomentType.TACTICAL_SHIFT and m.clock_ms < settings.spotter_min_window_ms
    ]
    assert opening == []


def test_no_shift_in_the_two_minutes_after_a_goal(spotted):
    goals = [e.clock_ms for e in spotted.events if e.outcome is Outcome.GOAL]
    assert goals
    flooded = [
        m
        for m in spotted.moments
        if m.type is MomentType.TACTICAL_SHIFT
        and any(0 < m.clock_ms - g < 2 * MINUTE for g in goals)
    ]
    assert flooded == []


def test_moment_ids_are_unique(spotted):
    ids = [m.moment_id for m in spotted.moments]
    assert len(ids) == len(set(ids))


def test_moments_name_the_model_and_version_that_made_them(spotted):
    assert all(m.model and m.model_version for m in spotted.moments)


def test_every_moment_names_an_epoch_the_match_has(spotted, request):
    match = played(request.node.callspec.params["spotted"], 1)
    epoch_ids = {e.epoch_id for e in detect(match_reader(match))}
    assert {m.epoch_id for m in spotted.moments} <= epoch_ids


def test_the_same_seed_gives_the_same_moments(spotted, request):
    again = _spot(played(request.node.callspec.params["spotted"], 1))
    assert again.moments == spotted.moments


def test_a_frame_never_fires_a_moment():
    match = played("comeback", 1)
    ingest = Ingest()
    understanding = Understanding(ingest.record)
    spotter = Spotter(ingest.record, understanding.epoch_at)
    for item in match.items[:300]:
        ingest.accept(item)
        if isinstance(item, MatchSetup):
            continue
        results = spotter.consider(understanding.observe(item), item)
        if isinstance(item, Frame):
            assert results == []


def test_spotting_is_entered(started):
    fresh, quiet = started
    with calltrace.recording() as entered:
        fresh().consider([], quiet)
    assert "Spotting" in entered


def test_prevent_identical_reading_to_fire_multiple_times() -> None:
    match = played("comeback", 1)
    ingest = Ingest()
    understanding = Understanding(ingest.record)
    spotter = Spotter(ingest.record, understanding.epoch_at)
    moments = []
    for item in match.items:
        ingest.accept(item)
        if isinstance(item, MatchSetup):
            continue
        moments += [r.moment for r in spotter.consider(understanding.observe(item), item)]
    cited = [i for m in moments for i in (*m.trigger_reading_ids, *m.trigger_event_ids)]
    assert cited
    assert len(cited) == len(set(cited))
