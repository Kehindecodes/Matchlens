from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from matchlens.models import (
    Action,
    BodyPart,
    Event,
    Frame,
    Match,
    Outcome,
    Phase,
    Player,
    PlayerPosition,
    Team,
    normalise_event,
    normalise_frame,
    normalise_xy,
)


def make_team(team_id="t-home", *, is_home=True, direction=1):
    return Team(
        team_id=team_id,
        match_id="m-1",
        name="Northgate United" if is_home else "Riverside Town",
        short_name="NOR" if is_home else "RIV",
        formation="4-3-3",
        is_home=is_home,
        attack_direction_by_period={1: direction, 2: -direction},
    )


def make_match(teams=None):
    return Match(
        match_id="m-1",
        pitch_length_m=105.0,
        pitch_width_m=68.0,
        kickoff_at=datetime(2026, 10, 9, 15, 0, tzinfo=UTC),
        archetype_id="tight_contest",
        seed=7,
        teams=teams or (make_team(), make_team("t-away", is_home=False, direction=-1)),
    )


def make_player(**overrides):
    base = dict(
        player_id="p-9",
        team_id="t-home",
        shirt=9,
        name="Dale Okoro",
        position="ST",
        is_starter=True,
    )
    return Player(**{**base, **overrides})


def make_frame(**overrides):
    base = dict(
        seq=10,
        clock_ms=5_000,
        period=1,
        phase=Phase.IN_PLAY,
        ball_x=10.0,
        ball_y=-5.0,
        ball_z=0.2,
        ball_speed=8.5,
        carrier="p-9",
        players=(
            PlayerPosition("p-9", 12.0, -4.0, 3.1),
            PlayerPosition("p-3", -20.0, 8.0, 1.0),
        ),
    )
    return Frame(**{**base, **overrides})


def make_event(**overrides):
    base = dict(
        event_id="e-1",
        seq=11,
        clock_ms=5_200,
        period=1,
        action=Action.PASS,
        player="p-9",
        team="t-home",
        start_x=10.0,
        start_y=-5.0,
        end_x=25.0,
        end_y=3.0,
        outcome=Outcome.COMPLETE,
        receiver="p-10",
        under_pressure=False,
        body_part=BodyPart.RIGHT_FOOT,
        frame_ref=10,
        player_on=None,
    )
    return Event(**{**base, **overrides})


def make_match_event(action, **overrides):
    """A roster or clock event: positional fields are null."""
    base = dict(
        event_id="e-m",
        seq=12,
        clock_ms=3_480_000,
        period=2,
        action=action,
        player="p-9",
        team="t-home",
        start_x=None,
        start_y=None,
        end_x=None,
        end_y=None,
        outcome=None,
        receiver=None,
        under_pressure=None,
        body_part=None,
        frame_ref=10,
        player_on=None,
    )
    return Event(**{**base, **overrides})


# --- round trips -------------------------------------------------------------


@pytest.mark.parametrize(
    "build", [make_match, make_player, make_frame, make_event, make_team], ids=lambda f: f.__name__
)
def test_json_round_trip(build):
    m = build()
    assert type(m).model_validate_json(m.model_dump_json()) == m


def test_frame_players_serialise_as_positional_arrays():
    import json

    dumped = json.loads(make_frame().model_dump_json())
    assert dumped["players"][0] == ["p-9", 12.0, -4.0, 3.1]


def test_frame_player_accessor_names_the_fields():
    pos = make_frame().players[0]
    assert (pos.player_id, pos.x, pos.y, pos.speed) == ("p-9", 12.0, -4.0, 3.1)


def test_frame_player_count_is_not_fixed_at_22():
    assert len(make_frame().players) == 2


# --- closed sets -------------------------------------------------------------


@pytest.mark.parametrize(
    "build, field",
    [
        (make_frame, "phase"),
        (make_event, "action"),
        (make_event, "outcome"),
        (make_event, "body_part"),
    ],
)
def test_invalid_enum_value_raises(build, field):
    with pytest.raises(ValidationError):
        build(**{field: "not_a_value"})


def test_unknown_field_raises():
    with pytest.raises(ValidationError):
        make_event(xg=0.3)


# --- Match -------------------------------------------------------------------


def test_match_requires_exactly_two_teams():
    home = make_team()
    away = make_team("t-away", is_home=False, direction=-1)
    third = make_team("t-third", is_home=False)
    with pytest.raises(ValidationError):
        make_match(teams=(home,))
    with pytest.raises(ValidationError):
        make_match(teams=(home, away, third))


def test_match_requires_one_home_team_and_consistent_match_id():
    with pytest.raises(ValidationError):
        make_match(teams=(make_team(), make_team("t-away", direction=-1)))
    stray = make_team("t-away", is_home=False).model_copy(update={"match_id": "other"})
    with pytest.raises(ValidationError):
        make_match(teams=(make_team(), stray))


def test_models_are_immutable_after_construction():
    with pytest.raises(ValidationError):
        make_event().clock_ms = 0


# --- Event / Frame -----------------------------------------------------------


def test_event_requires_a_frame_ref():
    data = make_event().model_dump()
    del data["frame_ref"]
    with pytest.raises(ValidationError):
        Event(**data)


def test_non_shot_events_may_omit_body_part_and_receiver():
    e = make_event(action=Action.TACKLE, receiver=None, body_part=None)
    assert e.receiver is None and e.body_part is None


def test_clock_is_a_non_negative_int_of_milliseconds():
    with pytest.raises(ValidationError):
        make_event(clock_ms=-1)
    with pytest.raises(ValidationError):
        make_frame(clock_ms=1.5)


def test_frame_carrier_must_be_on_the_frame():
    with pytest.raises(ValidationError):
        make_frame(carrier="p-99")
    assert make_frame(carrier=None).carrier is None


# --- Player (identity only, D16) ----------------------------------------------


@pytest.mark.parametrize("field", ["on_clock_ms", "off_clock_ms"])
def test_player_rejects_mutable_pitch_time_fields(field):
    with pytest.raises(ValidationError):
        make_player(**{field: 0})


def test_match_rejects_stored_period_boundaries():
    data = make_match().model_dump()
    with pytest.raises(ValidationError):
        Match(**data, period_boundaries=())


# --- match events (D16) --------------------------------------------------------


def test_player_on_is_set_only_for_substitutions():
    sub = make_match_event(Action.SUBSTITUTION, player_on="p-14")
    assert sub.player_on == "p-14"
    assert make_event().player_on is None
    for action in (Action.RED_CARD, Action.YELLOW_CARD):
        with pytest.raises(ValidationError):
            make_match_event(action, player_on="p-14")
    with pytest.raises(ValidationError):
        make_event(player_on="p-14")


def test_substitution_without_a_replacement_is_legal():
    assert make_match_event(Action.SUBSTITUTION).player_on is None


@pytest.mark.parametrize(
    "action",
    [
        Action.SUBSTITUTION,
        Action.RED_CARD,
        Action.YELLOW_CARD,
        Action.PERIOD_START,
        Action.PERIOD_END,
    ],
)
def test_match_events_round_trip_with_null_positional_fields(action):
    kwargs = (
        {"player": None, "team": None} if action in (Action.PERIOD_START, Action.PERIOD_END) else {}
    )
    e = make_match_event(action, **kwargs)
    assert Event.model_validate_json(e.model_dump_json()) == e


@pytest.mark.parametrize("field", ["start_x", "start_y", "end_x", "end_y"])
def test_match_events_must_not_carry_positions(field):
    with pytest.raises(ValidationError):
        make_match_event(Action.RED_CARD, **{field: 1.0})


@pytest.mark.parametrize(
    "field", ["start_x", "end_y", "outcome", "under_pressure", "player", "team"]
)
def test_on_ball_events_require_positions_outcome_and_actors(field):
    with pytest.raises(ValidationError):
        make_event(**{field: None})


def test_period_events_have_no_actor_but_cards_and_substitutions_do():
    assert make_match_event(Action.PERIOD_END, player=None, team=None).player is None
    for action in (Action.SUBSTITUTION, Action.RED_CARD, Action.YELLOW_CARD):
        with pytest.raises(ValidationError):
            make_match_event(action, player=None)


# --- coordinate normalisation ------------------------------------------------


def test_normalise_xy_flips_both_axes_when_attacking_negative_x():
    assert normalise_xy(10.0, -5.0, direction=1) == (10.0, -5.0)
    assert normalise_xy(10.0, -5.0, direction=-1) == (-10.0, 5.0)


def test_normalise_event_is_pure_and_uses_the_teams_direction_for_the_period():
    away = make_team("t-away", is_home=False, direction=-1)
    e = make_event(team="t-away", period=1)
    before = e.model_dump()

    out = normalise_event(e, away)

    assert e.model_dump() == before  # input unchanged
    assert out is not e
    assert (out.start_x, out.start_y, out.end_x, out.end_y) == (-10.0, 5.0, -25.0, -3.0)
    # second half the away team attacks +x, so nothing flips
    second = make_event(team="t-away", period=2)
    assert normalise_event(second, away).start_x == second.start_x


def test_normalise_frame_is_pure():
    away = make_team("t-away", is_home=False, direction=-1)
    f = make_frame()
    before = f.model_dump()

    out = normalise_frame(f, away)

    assert f.model_dump() == before
    assert (out.ball_x, out.ball_y, out.ball_z) == (-10.0, 5.0, 0.2)
    assert out.players[0] == PlayerPosition("p-9", -12.0, 4.0, 3.1)


def test_normalise_rejects_a_period_the_team_has_no_direction_for():
    with pytest.raises(KeyError):
        normalise_event(make_event(period=3), make_team())


def test_normalise_event_leaves_a_match_event_unchanged():
    away = make_team("t-away", is_home=False, direction=-1)
    card = make_match_event(Action.RED_CARD, team="t-away")
    assert normalise_event(card, away) == card
