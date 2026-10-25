"""Checks each claim against the untouched record and returns a verdict"""

import time
from collections.abc import Callable, Sequence

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan

from matchlens import calltrace
from matchlens.config import settings
from matchlens.models import (
    CheckName,
    CheckResult,
    CheckStatus,
    Claim,
    Moment,
    Verdict,
    Verification,
)
from matchlens.verification import checks
from matchlens.verification.record import Record

__all__ = ["MODEL", "MODEL_VERSION", "Record", "verify"]

MODEL = "verifier"
MODEL_VERSION = "checks-1"  # bump by hand whenever a check below changes (invariant 7)

tracer = trace.get_tracer(__name__)


def verify(claim: Claim, moment: Moment, claims: Sequence[Claim], record: Record) -> Verification:
    """The verdict on one claim of `moment`, whose claims are `claims`, checked against `record`.

    All six checks run, every time. It fails closed: a check that raises fails with the error
    as its reason, a claim that does not validate fails every check, and once the claim has
    used up `verifier_budget_ms` the checks still to run fail without running. The answer is
    never a pass by default, and never no record. Nothing about the claim is changed.
    """
    with tracer.start_as_current_span(
        "verification", attributes={"moment_id": claim.moment_id, "claim_id": claim.claim_id}
    ) as span:
        calltrace.entered("Verification")
        results, recomputed = _run(claim, moment, claims, record)
        failures = [
            f"{name}: {r.reason}" for name, r in results.items() if r.status is CheckStatus.FAILED
        ]
        verdict = Verdict.FAIL if failures else Verdict.PASS
        span.set_attribute("verdict", verdict.value)
    # Built after the span ends, so latency_ms is the span's own duration (S6).
    return Verification(
        verification_id=f"{claim.claim_id}:v",
        claim_id=claim.claim_id,
        verdict=verdict,
        checks=results,
        recomputed_value=recomputed,
        failure_reason="; ".join(failures) if failures else None,
        latency_ms=_duration_ms(span),
        model=MODEL,
        model_version=MODEL_VERSION,
    )


def _run(
    claim: Claim, moment: Moment, claims: Sequence[Claim], record: Record
) -> tuple[dict[CheckName, CheckResult], tuple[float, ...]]:
    try:
        Claim.model_validate(claim.model_dump())  # a claim built without validation is re-judged
        if claim.moment_id != moment.moment_id:
            raise ValueError(f"the claim is about {claim.moment_id}, not {moment.moment_id}")
    except Exception as malformed:
        return dict.fromkeys(CheckName, checks.failed(f"malformed claim: {malformed}")), ()

    recomputed: tuple[float, ...] = ()

    def value() -> CheckResult:
        nonlocal recomputed
        result, recomputed = checks.value_(claim, record)
        return result

    plan: dict[CheckName, Callable[[], CheckResult]] = {
        CheckName.CITATION: lambda: checks.citation(claim, record),
        CheckName.TEMPORAL: lambda: checks.temporal(claim, moment, record),
        CheckName.ENTITY: lambda: checks.entity(claim, record),
        CheckName.VALUE: value,
        CheckName.ENTAILMENT: lambda: checks.entailment(claim, record),
        CheckName.COVERAGE: lambda: checks.coverage(moment, claims),
    }
    deadline = time.perf_counter() + settings.verifier_budget_ms / 1000
    results: dict[CheckName, CheckResult] = {}
    for name, check in plan.items():
        if time.perf_counter() > deadline:
            results[name] = checks.failed(
                f"not run: the claim used up its {settings.verifier_budget_ms} ms budget"
            )
            continue
        try:
            results[name] = check()
        except Exception as error:
            results[name] = checks.failed(f"the check raised {error!r}")
    return results, recomputed


def _duration_ms(span: trace.Span) -> int:
    """A finished span's duration; 0 when tracing is off and the span recorded nothing."""
    if isinstance(span, ReadableSpan) and span.end_time is not None and span.start_time is not None:
        return (span.end_time - span.start_time) // 1_000_000
    return 0
