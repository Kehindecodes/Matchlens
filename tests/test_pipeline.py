from apps.pipeline import _passing
from matchlens.models import (
    CheckName,
    CheckResult,
    CheckStatus,
    Claim,
    ClaimType,
    Operand,
    Ref,
    RefKind,
    Verdict,
    Verification,
    Window,
)


def _claim(claim_id: str) -> Claim:
    operand = Operand(
        subject=Ref(kind=RefKind.TEAM, id="h"), metric="shots",
        window=Window(start_ms=0, end_ms=1), value=1.0,
        evidence_ids=(Ref(kind=RefKind.EVENT, id="ev-1"),),
    )  # fmt: skip
    return Claim(
        claim_id=claim_id, moment_id="m", claim_type=ClaimType.DESCRIPTIVE, operands=(operand,),
        backing_reading=None, threshold=None, model="m", model_version="v",
    )  # fmt: skip


def _verdict(claim_id: str, verdict: Verdict) -> Verification:
    status = CheckStatus.PASSED if verdict is Verdict.PASS else CheckStatus.FAILED
    checks = dict.fromkeys(CheckName, CheckResult(status=status, reason="r"))
    return Verification(
        verification_id=f"{claim_id}:v", claim_id=claim_id, verdict=verdict, checks=checks,
        recomputed_value=(), failure_reason=None if verdict is Verdict.PASS else "r",
        latency_ms=0, model="verifier", model_version="0",
    )  # fmt: skip


def test_only_claims_that_passed_go_on():
    claims = [_claim("a"), _claim("b")]
    verdicts = [_verdict("a", Verdict.PASS), _verdict("b", Verdict.FAIL)]
    assert [c.claim_id for c in _passing(claims, verdicts)] == ["a"]


def test_a_claim_with_no_verification_does_not_go_on():
    assert _passing([_claim("a")], []) == []
