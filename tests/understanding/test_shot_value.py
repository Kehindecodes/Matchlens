"""U2: shot quality, a hand-calibrated lookup over distance and angle. Never called xG."""

import ast
import inspect

import pytest

from matchlens.models import Action, BodyPart, Event, Match, Outcome
from matchlens.understanding import shot_value
from matchlens.understanding.shot_value import (
    MODEL_VERSION,
    PENALTY_VALUE,
    calibration_fingerprint,
    is_shot,
    quality,
    value,
    values,
)

DISTANCES = [d / 2 for d in range(0, 121)]  # 0 to 60 m
ANGLES = [float(a) for a in range(0, 91)]  # degrees off the goal's centre line


def _shot(match: Match, x: float, y: float, period: int = 1, action=Action.SHOT) -> Event:
    team = match.teams[0]
    return Event(
        event_id="s", seq=0, clock_ms=0, period=period, action=action, player="p",
        team=team.team_id, start_x=x, start_y=y, end_x=x, end_y=y, outcome=Outcome.SAVED,
        receiver=None, player_on=None, added_time_ms=None, under_pressure=False,
        body_part=BodyPart.RIGHT_FOOT, frame_ref=0,
    )  # fmt: skip


def _towards_goal(match: Match, period: int, along: float, across: float) -> tuple[float, float]:
    """A point `along` metres out from the goal team 0 attacks in `period`, `across` off centre."""
    direction = match.teams[0].attack_direction(period)
    half = match.pitch_length_m / 2
    return direction * (half - along), direction * across


def test_every_shot_in_a_match_has_exactly_one_value(played):
    shots = [e for e in played.events if is_shot(e)]
    valued = values(played.events, played.setup.match)
    assert shots
    assert [v.event_id for v in valued] == [e.event_id for e in shots]


def test_direct_free_kicks_at_goal_are_shots_and_free_kick_passes_are_not(played):
    kick = _shot(played.setup.match, 30.0, 5.0, action=Action.FREE_KICK)

    def is_shot_with(outcome: Outcome) -> bool:
        return is_shot(kick.model_copy(update={"outcome": outcome}))

    at_goal = (Outcome.SAVED, Outcome.GOAL, Outcome.OFF_TARGET, Outcome.BLOCKED)
    assert all(is_shot_with(o) for o in at_goal)
    assert not any(is_shot_with(o) for o in (Outcome.COMPLETE, Outcome.INCOMPLETE))


def test_values_stay_in_the_unit_interval_at_extreme_coordinates(played):
    match = played.setup.match
    half_l, half_w = match.pitch_length_m / 2, match.pitch_width_m / 2
    for x in (-half_l - 50, -half_l, 0.0, half_l, half_l + 50):
        for y in (-half_w - 50, -half_w, 0.0, half_w, half_w + 50):
            v = value(_shot(match, x, y), match)
            assert 0.0 <= v.value <= 1.0


def test_value_never_rises_as_the_shot_moves_further_out():
    for angle in ANGLES:
        row = [quality(d, angle) for d in DISTANCES]
        assert all(a >= b for a, b in zip(row, row[1:], strict=False)), f"angle {angle}"


def test_value_never_rises_as_the_angle_tightens():
    for distance in DISTANCES:
        row = [quality(distance, a) for a in ANGLES]
        assert all(a >= b for a, b in zip(row, row[1:], strict=False)), f"distance {distance}"


def test_the_lookup_is_plausible_at_the_ends():
    assert quality(2.0, 0.0) > 0.5  # a tap-in
    assert quality(27.0, 0.0) < 0.06  # thirty yards, central
    assert quality(6.0, 70.0) < quality(6.0, 0.0) / 2  # tight angle at the same distance


def test_a_penalty_is_the_penalty_constant_not_the_lookup(played):
    match = played.setup.match
    x, y = _towards_goal(match, 1, 11.0, 0.0)
    penalty = value(_shot(match, x, y, action=Action.PENALTY), match)
    assert penalty.value == PENALTY_VALUE
    assert penalty.value != quality(11.0, 0.0)


def test_distance_and_angle_are_kept_and_explain_the_value(played):
    match = played.setup.match
    x, y = _towards_goal(match, 1, 12.0, 5.0)
    v = value(_shot(match, x, y), match)
    assert v.distance == pytest.approx(13.0)
    assert v.angle == pytest.approx(22.62, abs=0.01)
    assert v.value == quality(v.distance, v.angle)
    assert v.model_version == MODEL_VERSION


def test_a_second_half_shot_is_normalised(played):
    """The same spot relative to the goal attacked is worth the same in either half."""
    match = played.setup.match
    first = value(_shot(match, *_towards_goal(match, 1, 16.0, -7.0), period=1), match)
    second = value(_shot(match, *_towards_goal(match, 2, 16.0, -7.0), period=2), match)
    assert (second.value, second.distance, second.angle) == (
        first.value, first.distance, first.angle
    )  # fmt: skip
    assert first.distance < 20  # not measured from the wrong goal


def test_the_module_is_pure_and_uses_no_randomness(played):
    tree = ast.parse(inspect.getsource(shot_value))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom)
                for a in n.names}  # fmt: skip
    assert not ({"random", "numpy", "rng"} & (names | imported))
    assert values(played.events, played.setup.match) == values(played.events, played.setup.match)


def test_changing_the_calibration_needs_a_new_model_version():
    """If this fails, you changed the lookup: bump MODEL_VERSION and update both values here."""
    assert (MODEL_VERSION, calibration_fingerprint()) == ("shot-quality-2", "2d8873cc4cf3")


def test_a_non_shot_is_refused(played):
    a_pass = next(e for e in played.events if e.action is Action.PASS)
    with pytest.raises(ValueError):
        value(a_pass, played.setup.match)
