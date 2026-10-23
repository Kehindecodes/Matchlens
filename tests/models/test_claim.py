import pytest
from pydantic import ValidationError

from matchlens.models import Claim, ClaimType, Metric, Operand, Ref, RefKind, Window

HOME = Ref(kind=RefKind.TEAM, id="m-1-home")
AWAY = Ref(kind=RefKind.TEAM, id="m-1-away")
READING = Ref(kind=RefKind.READING, id="r-pressing_intensity-away-4039535")


def _events(*ids: str) -> tuple[Ref, ...]:
    return tuple(Ref(kind=RefKind.EVENT, id=i) for i in ids)


def _operand(**overrides) -> Operand:
    fields = dict(
        subject=HOME, metric=Metric.CHANCES,
        window=Window(start_ms=3_439_535, end_ms=4_039_535), value=9.0,
        evidence_ids=_events("ev-1601", "ev-1622"),
    )  # fmt: skip
    return Operand.model_validate(fields | overrides)


def _claim(**overrides) -> Claim:
    fields = dict(
        claim_id="c1", moment_id="m1", claim_type=ClaimType.DESCRIPTIVE, operands=(_operand(),),
        backing_reading=None, threshold=None, model="explainer-model", model_version="v1",
    )  # fmt: skip
    return Claim.model_validate(fields | overrides)


# --- the three types ------------------------------------------------------------------------------


def test_a_descriptive_claim_has_one_operand():
    assert len(_claim().operands) == 1


def test_a_comparative_claim_has_two_operands_each_with_its_own_window_and_evidence():
    before = _operand(
        window=Window(start_ms=2_839_535, end_ms=3_439_535), value=3.0,
        evidence_ids=_events("ev-1402"),
    )  # fmt: skip
    claim = _claim(claim_type=ClaimType.COMPARATIVE, operands=(_operand(), before))
    assert [o.value for o in claim.operands] == [9.0, 3.0]
    assert claim.operands[0].window != claim.operands[1].window


def test_an_interpretive_claim_is_backed_by_a_reading_and_a_threshold():
    pressing = _operand(
        subject=AWAY, metric=Metric.PRESSING_INTENSITY, value=-2.4, evidence_ids=(READING,)
    )
    claim = _claim(
        claim_type=ClaimType.INTERPRETIVE, operands=(pressing,),
        backing_reading=READING, threshold=-2.0,
    )  # fmt: skip
    assert claim.threshold == -2.0


# --- the rules ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("claim_type", "count"),
    [(ClaimType.DESCRIPTIVE, 2), (ClaimType.COMPARATIVE, 1), (ClaimType.INTERPRETIVE, 2)],
)
def test_the_operand_count_must_match_the_claim_type(claim_type, count):
    extra = {"backing_reading": READING, "threshold": -2.0}
    with pytest.raises(ValidationError, match="operand"):
        _claim(
            claim_type=claim_type,
            operands=(_operand(),) * count,
            **(extra if claim_type is ClaimType.INTERPRETIVE else {}),
        )


def test_an_operand_with_no_evidence_cannot_be_made():
    with pytest.raises(ValidationError):
        _operand(evidence_ids=())


def test_evidence_is_events_readings_or_runs():
    with pytest.raises(ValidationError, match="evidence is events"):
        _operand(evidence_ids=(HOME,))


def test_an_operand_is_about_a_team_or_a_player():
    with pytest.raises(ValidationError, match="team or a player"):
        _operand(subject=READING)


def test_a_window_cannot_start_after_it_ends():
    with pytest.raises(ValidationError, match="start after it ends"):
        Window(start_ms=10, end_ms=5)


def test_an_interpretive_claim_without_a_reading_or_threshold_is_refused():
    with pytest.raises(ValidationError, match="backing_reading"):
        _claim(claim_type=ClaimType.INTERPRETIVE, threshold=-2.0)
    with pytest.raises(ValidationError, match="threshold"):
        _claim(claim_type=ClaimType.INTERPRETIVE, backing_reading=READING)


def test_only_an_interpretive_claim_is_backed():
    with pytest.raises(ValidationError, match="backing_reading"):
        _claim(backing_reading=READING, threshold=-2.0)


def test_the_backing_must_be_a_signal_reading():
    with pytest.raises(ValidationError, match="backed by a signal reading"):
        _claim(
            claim_type=ClaimType.INTERPRETIVE,
            backing_reading=Ref(kind=RefKind.EVENT, id="ev-1"),
            threshold=-2.0,
        )
