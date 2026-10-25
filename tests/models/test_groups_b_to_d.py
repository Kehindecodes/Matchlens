from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from matchlens.models import (
    ClaimType,
    Depth,
    DetailLevel,
    EpochTrigger,
    Lens,
    Moment,
    MomentType,
    OverlayTemplate,
    Possession,
    PossessionOutcome,
    ProducerAction,
    ProducerActionType,
    Ref,
    RefKind,
    Rendition,
    Scope,
    ShotValue,
    Signal,
    SignalReading,
    SuppressionReason,
    Trend,
    Zone,
)

NOW = datetime(2026, 10, 11, tzinfo=UTC)


def test_group_b_to_d_enum_values_match_the_data_model():
    assert {z.value for z in Zone} == {"defensive_third", "middle_third", "final_third"}
    assert {o.value for o in PossessionOutcome} == {
        "shot",
        "turnover",
        "foul",
        "out_of_play",
        "period_end",
    }
    assert {s.value for s in Signal} == {
        "territory", "possession_control", "pressing_intensity", "chance_quality", "line_height",
    }  # fmt: skip
    assert {t.value for t in Trend} == {"rising", "falling", "steady"}
    assert {t.value for t in EpochTrigger} == {"goal", "red_card", "half_time"}
    assert {t.value for t in MomentType} == {
        "goal", "chance", "tactical_shift", "milestone", "pattern",
    }  # fmt: skip
    assert {t.value for t in ClaimType} == {"descriptive", "comparative", "interpretive"}
    assert {s.value for s in Scope} == {"match", "team", "player"}
    assert {d.value for d in Depth} == {"casual", "engaged", "analyst"}
    assert {d.value for d in DetailLevel} == {"minimal", "standard", "full"}
    assert {a.value for a in ProducerActionType} == {"suppress", "hold", "release", "pin"}
    assert {t.value for t in OverlayTemplate} == {"lower_third", "stat_bar", "team_card"}


def test_suppression_reasons_are_declared_in_evaluation_order():
    assert [r.value for r in SuppressionReason] == [
        "out_of_scope", "muted", "degraded", "verification_failed", "claims_filtered_out",
        "below_threshold", "rate_limited",
    ]  # fmt: skip


# --- group B --------------------------------------------------------------------------------------


def _reading(**overrides) -> SignalReading:
    fields = dict(
        reading_id="r1", signal=Signal.TERRITORY, team="home", clock_ms=600_000,
        window_ms=300_000, value=0.6, baseline=0.5, z_match=1.2, z_prior=0.3,
        trend=Trend.RISING, confidence=0.8, epoch_id="e1",
    )  # fmt: skip
    return SignalReading.model_validate(fields | overrides)


def test_a_reading_is_frozen():
    with pytest.raises(ValidationError):
        _reading().value = 1.0  # type: ignore[misc]


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_reading_confidence_is_a_unit_interval(confidence):
    with pytest.raises(ValidationError):
        _reading(confidence=confidence)


def test_a_possession_cites_at_least_one_event():
    with pytest.raises(ValidationError):
        Possession(
            possession_id="p1", team="home", start_clock_ms=0, end_clock_ms=10_000,
            pass_count=0, start_zone=Zone.DEFENSIVE_THIRD, end_zone=Zone.MIDDLE_THIRD,
            outcome=PossessionOutcome.TURNOVER, event_ids=(),
        )  # fmt: skip


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_shot_quality_is_a_unit_interval(value):
    with pytest.raises(ValidationError):
        ShotValue(event_id="ev1", value=value, distance=12.0, angle=0.4, model_version="v1")


# --- group C --------------------------------------------------------------------------------------


def _moment(**overrides) -> Moment:
    fields = dict(
        moment_id="m1", clock_ms=600_000, type=MomentType.CHANCE,
        subject=Ref(kind=RefKind.TEAM, id="home"), importance=0.7,
        trigger_reading_ids=("r1",), trigger_event_ids=(), epoch_id="e1",
        model="spotter", model_version="0",
    )  # fmt: skip
    return Moment.model_validate(fields | overrides)


@pytest.mark.parametrize("kind", [RefKind.TEAM, RefKind.PLAYER])
def test_a_moment_is_about_a_team_or_a_player(kind):
    assert _moment(subject=Ref(kind=kind, id="x")).subject.kind is kind


@pytest.mark.parametrize("kind", [RefKind.EVENT, RefKind.READING, RefKind.LENS])
def test_a_moment_is_not_about_anything_else(kind):
    with pytest.raises(ValidationError, match="team or a player"):
        _moment(subject=Ref(kind=kind, id="x"))


def test_a_moment_cites_what_fired_it():
    with pytest.raises(ValidationError, match="cite"):
        _moment(trigger_reading_ids=(), trigger_event_ids=())


def _rendition(**overrides) -> Rendition:
    fields = dict(
        rendition_id="m1:casual", moment_id="m1", lens_id="casual", language="en",
        headline="Home are camped in the final third", body="...", surviving_claim_ids=("c1",),
        suppressed=False, suppression_reason=None, rendered_at=NOW, model="templates",
        model_version="t",
    )  # fmt: skip
    return Rendition.model_validate(fields | overrides)


def _silent(**overrides) -> Rendition:
    fields = dict(
        headline=None, body=None, surviving_claim_ids=(), suppressed=True,
        suppression_reason=SuppressionReason.BELOW_THRESHOLD,
    )  # fmt: skip
    return _rendition(**(fields | overrides))


def test_a_suppressed_rendition_is_a_record():
    assert _silent().suppression_reason is SuppressionReason.BELOW_THRESHOLD


def test_suppressed_needs_a_reason():
    with pytest.raises(ValidationError, match="iff suppressed"):
        _silent(suppression_reason=None)


def test_a_shown_rendition_has_no_reason():
    with pytest.raises(ValidationError, match="iff suppressed"):
        _rendition(suppression_reason=SuppressionReason.MUTED)


@pytest.mark.parametrize(
    "overrides", [{"headline": "x"}, {"body": "x"}, {"surviving_claim_ids": ("c1",)}]
)
def test_silence_shows_nothing(overrides):
    with pytest.raises(ValidationError, match="shows nothing|no headline"):
        _silent(**overrides)


@pytest.mark.parametrize("missing", ["headline", "body"])
def test_a_shown_rendition_has_something_to_show(missing):
    with pytest.raises(ValidationError, match="needs a headline and a body"):
        _rendition(**{missing: None})


# --- group D --------------------------------------------------------------------------------------


def _lens(**overrides) -> Lens:
    fields = dict(
        lens_id="team_engaged", name="Team", audience="supporters", scope=Scope.TEAM,
        breakthrough_types=(MomentType.GOAL,), depth=Depth.ENGAGED, importance_threshold=0.5,
        max_cards_per_10min=3, allowed_claim_types=tuple(ClaimType),
        detail_level=DetailLevel.STANDARD,
        language="en", focus_team="home", focus_player=None,
    )  # fmt: skip
    return Lens.model_validate(fields | overrides)


def test_a_team_lens_needs_a_focus_team():
    with pytest.raises(ValidationError, match="focus_team"):
        _lens(focus_team=None)


def test_a_match_lens_has_no_focus_team():
    with pytest.raises(ValidationError, match="focus_team"):
        _lens(scope=Scope.MATCH)


def test_a_match_lens_needs_no_focus():
    assert _lens(scope=Scope.MATCH, focus_team=None).focus_team is None


def test_a_player_lens_needs_a_focus_player():
    with pytest.raises(ValidationError, match="focus_player"):
        _lens(scope=Scope.PLAYER, focus_team=None)


@pytest.mark.parametrize("kind", [RefKind.MOMENT, RefKind.RENDITION, RefKind.LENS])
def test_a_producer_acts_on_a_moment_rendition_or_lens(kind):
    action = ProducerAction(
        action_id="a1", target_id=Ref(kind=kind, id="x"), action=ProducerActionType.SUPPRESS,
        actor="producer", clock_ms=0, reason=None,
    )  # fmt: skip
    assert action.target_id.kind is kind


def test_a_producer_cannot_act_on_a_team():
    with pytest.raises(ValidationError, match="targets a moment"):
        ProducerAction(
            action_id="a1", target_id=Ref(kind=RefKind.TEAM, id="home"),
            action=ProducerActionType.PIN, actor="producer", clock_ms=0, reason=None,
        )  # fmt: skip
