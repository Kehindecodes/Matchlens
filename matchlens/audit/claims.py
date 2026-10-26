"""The rejected-claims view (P3): every claim of the match with its verdict and its six checks.

It reads what Audit holds and nothing else. No check is run again and no value is recomputed
here: a figure on the page is a figure A3 stored, and a reason is the reason A3 wrote, word for
word. Everything is sent already worded, so the browser has nothing to work out and cannot agree
with itself while the pipeline is wrong.
"""

import math

from pydantic import BaseModel, ConfigDict

from matchlens.audit import Audit, Audited
from matchlens.models import CheckName, CheckStatus, Claim, Operand, Verdict, Verification

__all__ = ["ClaimsPage", "claims_page"]


class _Row(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class OperandRow(_Row):
    subject: str  # the team's or player's name, or its id if the match never introduced it
    metric: str
    window: str
    claimed: str
    recomputed: str | None  # A3's figure for this operand; None where it could not make one


class CheckRow(_Row):
    check: CheckName
    status: CheckStatus  # passed, failed or not applicable: three states, never two
    reason: str | None  # A3's own words, for a failure


class ClaimRow(_Row):
    claim_id: str
    claim_type: str
    said_by: str  # whatever proposed the claim, with its version (invariant 7)
    checked_by: str  # whatever judged it
    verdict: Verdict
    failure_reason: str | None
    operands: list[OperandRow]
    checks: list[CheckRow]


class MomentRow(_Row):
    moment_id: str
    clock: str
    moment_type: str
    claims: list[ClaimRow]


class Totals(_Row):
    claims: int
    rejected: int


class ClaimsPage(_Row):
    """The moments recorded after the reader's last, and the whole trail's totals.

    `recorded` is how many moments Audit holds, claims or not: the `after` to ask with next time.
    """

    recorded: int
    totals: Totals
    moments: list[MomentRow]


def claims_page(audit: Audit, after: int = 0) -> ClaimsPage:
    """The claims of the moments recorded after the `after`-th, and the totals over all of them."""
    trail = audit.trail()
    names = audit.names
    return ClaimsPage(
        recorded=len(trail),
        totals=_totals(trail),
        moments=[_moment_row(entry, names) for entry in trail[max(0, after) :] if entry.claims],
    )


def _totals(trail: tuple[Audited, ...]) -> Totals:
    claims = rejected = 0
    for entry in trail:
        verdicts = _verdicts(entry)
        claims += len(entry.claims)
        rejected += sum(
            verdicts[claim.claim_id].verdict is not Verdict.PASS for claim in entry.claims
        )
    return Totals(claims=claims, rejected=rejected)


def _verdicts(entry: Audited) -> dict[str, Verification]:
    return {verification.claim_id: verification for verification in entry.verifications}


def _moment_row(entry: Audited, names: dict[str, str]) -> MomentRow:
    verdicts = _verdicts(entry)
    return MomentRow(
        moment_id=entry.moment.moment_id,
        clock=_clock(entry.moment.clock_ms),
        moment_type=entry.moment.type.value,
        claims=[_claim_row(claim, verdicts[claim.claim_id], names) for claim in entry.claims],
    )


def _claim_row(claim: Claim, verdict: Verification, names: dict[str, str]) -> ClaimRow:
    figures = list(verdict.recomputed_value)
    return ClaimRow(
        claim_id=claim.claim_id,
        claim_type=claim.claim_type.value,
        said_by=f"{claim.model} {claim.model_version}",
        checked_by=f"{verdict.model} {verdict.model_version}",
        verdict=verdict.verdict,
        failure_reason=verdict.failure_reason,
        operands=[
            _operand_row(operand, figures[index] if index < len(figures) else math.nan, names)
            for index, operand in enumerate(claim.operands)
        ],
        checks=[
            CheckRow(
                check=name, status=verdict.checks[name].status, reason=verdict.checks[name].reason
            )
            for name in CheckName
        ],
    )


def _operand_row(operand: Operand, recomputed: float, names: dict[str, str]) -> OperandRow:
    window = operand.window
    return OperandRow(
        subject=names.get(operand.subject.id, operand.subject.id),
        metric=operand.metric.value,
        window=f"{_clock(window.start_ms)}–{_clock(window.end_ms)}",
        claimed=f"{operand.value:g}",
        recomputed=None if math.isnan(recomputed) else f"{recomputed:g}",
    )


def _clock(clock_ms: int) -> str:
    minutes, seconds = divmod(clock_ms // 1000, 60)
    return f"{minutes:02d}:{seconds:02d}"
