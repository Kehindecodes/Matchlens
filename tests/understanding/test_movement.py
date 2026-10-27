"""Q48: what the frames before a shot showed, measured by Understanding as position readings.

The recounts here are written apart from `movement.py`, from the frames each reading cites, so
the two can disagree.
"""

import math

import pytest

from matchlens.config import settings
from matchlens.ingest import Ingest
from matchlens.models import Event, Frame, Mechanism, PositionReading
from matchlens.source import simulate
from matchlens.understanding import Movement
from matchlens.understanding.shot_value import is_shot
from tests.source.helpers import Played, split


@pytest.fixture(scope="module")
def demo() -> Played:
    return split(list(simulate(1)))


@pytest.fixture(scope="module")
def readings(demo: Played) -> list[PositionReading]:
    ingest = Ingest()
    movement = Movement(ingest.frame_access, ingest.record)
    found = []
    for item in demo.items:
        ingest.accept(item)
        found += movement.observe(item)
    return found


def _frame(demo: Played, seq: int) -> Frame:
    return next(f for f in demo.frames if f.seq == seq)


def _at(frame: Frame, player_id: str) -> tuple[float, float]:
    position = next(p for p in frame.players if p.player_id == player_id)
    return position.x, position.y


def test_the_demo_match_shows_every_mechanism(readings):
    """The simulator's decoy runs (`generator-2`) are what make a decoy run there to be seen."""
    assert {r.mechanism for r in readings} == set(Mechanism)


def test_only_shots_are_measured_and_each_reading_is_taken_at_its_shot(demo, readings):
    by_id = {e.event_id: e for e in demo.events}
    for reading in readings:
        shot = by_id[reading.shot_id]
        assert is_shot(shot) and shot.team == reading.team
        assert reading.clock_ms == shot.clock_ms
        assert reading.start_ms <= reading.end_ms <= shot.clock_ms  # nothing after the shot


def test_each_reading_cites_the_frames_it_was_measured_from(demo, readings):
    clocks = {f.seq: f.clock_ms for f in demo.frames}
    for reading in readings:
        assert clocks[reading.frame_seqs[0]] == reading.start_ms
        assert clocks[reading.frame_seqs[-1]] == reading.end_ms


def test_an_overload_recounts_from_its_frame(demo, readings):
    roster = {p.player_id: p for p in demo.setup.players}
    overloads = [r for r in readings if r.mechanism is Mechanism.OVERLOAD]
    assert overloads
    for reading in overloads:
        [seq] = reading.frame_seqs
        frame = _frame(demo, seq)
        near = [
            roster[p.player_id].team_id
            for p in frame.players
            if roster[p.player_id].position != "GK"
            and math.dist((p.x, p.y), (frame.ball_x, frame.ball_y)) <= settings.movement_reach_m
        ]
        attackers = near.count(reading.team)
        assert (reading.value, reading.against) == (attackers, len(near) - attackers)
        assert reading.value > (reading.against or 0)


def test_a_decoy_run_went_away_from_the_shot_with_a_defender_beside_him(demo, readings):
    by_id: dict[str, Event] = {e.event_id: e for e in demo.events}
    roster = {p.player_id: p for p in demo.setup.players}
    runs = [r for r in readings if r.mechanism is Mechanism.DECOY_RUN]
    assert runs
    for run in runs:
        assert run.player is not None and run.opponent is not None
        assert roster[run.player].team_id == run.team != roster[run.opponent].team_id
        shot = by_id[run.shot_id]
        assert run.player != shot.player
        first, last = _frame(demo, run.frame_seqs[0]), _frame(demo, run.frame_seqs[-1])
        struck = (shot.start_x or 0.0, shot.start_y or 0.0)
        away = math.dist(_at(last, run.player), struck) - math.dist(_at(first, run.player), struck)
        assert away >= settings.movement_decoy_min_m
        assert math.dist(_at(last, run.player), _at(last, run.opponent)) <= (
            settings.movement_marker_end_m
        )
        drawn = math.dist(_at(first, run.opponent), _at(last, run.opponent))
        assert run.value == round(drawn, 1)


def test_an_early_run_is_the_shooter_covering_ground_before_the_pass(demo, readings):
    by_id = {e.event_id: e for e in demo.events}
    runs = [r for r in readings if r.mechanism is Mechanism.EARLY_RUN]
    assert runs
    for run in runs:
        assert run.player == by_id[run.shot_id].player
        first, last = _frame(demo, run.frame_seqs[0]), _frame(demo, run.frame_seqs[-1])
        covered = math.dist(_at(first, run.player), _at(last, run.player))
        assert run.value == round(covered, 1) >= settings.movement_early_min_m


def test_measuring_twice_gives_the_same_readings(demo, readings):
    """Seeded means deterministic (invariant 9), and the readings hold no state between shots."""
    ingest = Ingest()
    movement = Movement(ingest.frame_access, ingest.record)
    again = []
    for item in demo.items:
        ingest.accept(item)
        again += movement.observe(item)
    assert again == readings
