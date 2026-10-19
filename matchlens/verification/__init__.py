"""Checks each claim against the untouched record and returns a verdict"""

from collections.abc import Sequence

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan

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
tracer = trace.get_tracer(__name__)


def verify(claim: Claim, record: Sequence[Event]) -> Verification:
    """The verdict on one claim.

    Stub until A3: every check is recorded as not applicable, with that reason, so the verdict
    passes without the record claiming a check ran when it did not.
    """
    with tracer.start_as_current_span(
        "verification", attributes={"moment_id": claim.moment_id, "claim_id": claim.claim_id}
    ) as span:
        calltrace.entered("Verification")
        checks = dict.fromkeys(CheckName, _NOT_YET)
        verdict = Verdict.PASS
        span.set_attribute("verdict", verdict.value)
    # Built after the span ends, so latency_ms is the span's own duration (S6).
    return Verification(
        verification_id=f"{claim.claim_id}:v",
        claim_id=claim.claim_id,
        verdict=verdict,
        checks=checks,
        recomputed_value=(),
        failure_reason=None,
        latency_ms=_duration_ms(span),
        model="stub",
        model_version="S4",
    )


def _duration_ms(span: trace.Span) -> int:
    """A finished span's duration; 0 when tracing is off and the span recorded nothing."""
    if isinstance(span, ReadableSpan) and span.end_time is not None and span.start_time is not None:
        return (span.end_time - span.start_time) // 1_000_000
    return 0
