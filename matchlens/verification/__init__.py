"""Checks each claim against the untouched record and returns a verdict"""

from collections.abc import Sequence

from matchlens import calltrace
from matchlens.models import (
    CheckName,
    CheckResult,
    CheckStatus,
    Claim,
    Event,
    Verdict,
    Verification,
)

_NOT_YET = CheckResult(status=CheckStatus.NOT_APPLICABLE, reason="stub: A3 implements this check")


def verify(claim: Claim, record: Sequence[Event]) -> Verification:
    """The verdict on one claim.

    Stub until A3: every check is recorded as not applicable, with that reason, so the verdict
    passes without the record claiming a check ran when it did not.
    """
    calltrace.entered("Verification")
    return Verification(
        verification_id=f"{claim.claim_id}:v",
        claim_id=claim.claim_id,
        verdict=Verdict.PASS,
        checks=dict.fromkeys(CheckName, _NOT_YET),
        recomputed_value=(),
        failure_reason=None,
        latency_ms=0,
        model="stub",
        model_version="S4",
    )
