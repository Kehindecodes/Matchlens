import pytest
from pydantic import ValidationError

from matchlens.models import CheckName, CheckResult, CheckStatus, Verdict, Verification

PASSED = CheckResult(status=CheckStatus.PASSED)


def _checks(**overrides: CheckResult) -> dict[CheckName, CheckResult]:
    return {name: overrides.get(name.value, PASSED) for name in CheckName}


def _verification(**overrides) -> Verification:
    fields = dict(
        verification_id="v1", claim_id="c1", verdict=Verdict.PASS, checks=_checks(),
        recomputed_value=(9.0, 3.0), failure_reason=None, latency_ms=12,
        model="verifier", model_version="0.1",
    )  # fmt: skip
    return Verification.model_validate(fields | overrides)


def test_the_check_names_match_the_data_model():
    assert [c.value for c in CheckName] == [
        "citation", "temporal", "entity", "value", "entailment", "coverage",
    ]  # fmt: skip


def test_a_passing_verification():
    assert _verification().verdict is Verdict.PASS


def test_every_check_must_run():
    checks = _checks()
    del checks[CheckName.COVERAGE]
    with pytest.raises(ValidationError, match="every check must run"):
        _verification(checks=checks)


def test_not_applicable_counts_as_clear():
    entity = CheckResult(status=CheckStatus.NOT_APPLICABLE, reason="subject is a team")
    assert _verification(checks=_checks(entity=entity)).verdict is Verdict.PASS


def test_one_failed_check_makes_the_verdict_fail():
    value = CheckResult(status=CheckStatus.FAILED, reason="recount says 7, not 9")
    failed = _verification(
        checks=_checks(value=value), verdict=Verdict.FAIL, failure_reason="value: 7, not 9"
    )
    assert failed.checks[CheckName.VALUE].reason == "recount says 7, not 9"


def test_a_verdict_cannot_disagree_with_its_checks():
    value = CheckResult(status=CheckStatus.FAILED, reason="recount says 7, not 9")
    with pytest.raises(ValidationError, match="verdict is pass iff"):
        _verification(checks=_checks(value=value))  # says pass, a check failed
    with pytest.raises(ValidationError, match="verdict is pass iff"):
        _verification(verdict=Verdict.FAIL, failure_reason="x")  # says fail, nothing failed


def test_failure_reason_is_required_iff_the_verdict_is_fail():
    value = CheckResult(status=CheckStatus.FAILED, reason="r")
    with pytest.raises(ValidationError, match="failure_reason"):
        _verification(checks=_checks(value=value), verdict=Verdict.FAIL)
    with pytest.raises(ValidationError, match="failure_reason"):
        _verification(failure_reason="nothing failed")


def test_a_failed_check_needs_a_reason():
    with pytest.raises(ValidationError, match="needs a reason"):
        CheckResult(status=CheckStatus.FAILED)


def test_recomputed_value_can_be_empty_when_no_recount_ran():
    citation = CheckResult(status=CheckStatus.FAILED, reason="ev-9999 does not exist")
    v = _verification(
        checks=_checks(citation=citation), verdict=Verdict.FAIL,
        failure_reason="citation", recomputed_value=(),
    )  # fmt: skip
    assert v.recomputed_value == ()


def test_latency_is_never_negative():
    with pytest.raises(ValidationError):
        _verification(latency_ms=-1)
