"""What a card's evidence drawer shows: each claim behind it, and the rows it cites (A6, V7).

Built here, where the claims, their verifications and the record are all in hand, so the page
only displays. A drawer that worked out its own numbers could agree with itself while the
pipeline was wrong; every value below is copied from a claim, a verification or a record row.

The drawer is the audit view, on the demo page only (Q42: 1A). So unlike a card, it shows the
calibrated values as the record holds them: a shot's quality, a reading's `z_match`. A viewer's
page is never sent any of it: the stream carries cards without their evidence.

It lists every claim Selection kept for the lens, marked whether the card said it (Q42: 2A),
and nothing that is not evidence: no importance, no selection reason, no lens id.
"""

from collections.abc import Collection, Mapping, Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from matchlens.models import (
    CheckName,
    CheckStatus,
    Claim,
    ClaimType,
    ClockMs,
    Metric,
    Operand,
    Ref,
    RefKind,
    Signal,
    Verdict,
    Verification,
    Window,
)
from matchlens.verification.record import Record


class _Row(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CitedEvent(_Row):
    """An event a claim cites, as the match log holds it, with names for its ids."""

    kind: Literal["event"] = "event"
    event_id: str
    clock_ms: ClockMs
    period: int
    action: str
    team: str | None
    player: str | None
    outcome: str | None


class CitedReading(_Row):
    """A signal reading a claim cites, with the baseline its `z_match` is measured from."""

    kind: Literal["reading"] = "reading"
    reading_id: str
    signal: Signal
    team: str
    clock_ms: ClockMs
    window_ms: ClockMs
    value: float
    baseline: float
    z_match: float


Cited = Annotated[CitedEvent | CitedReading, Field(discriminator="kind")]


class OperandEvidence(_Row):
    subject: str
    metric: Metric
    value: float
    window: Window
    cited: Annotated[tuple[Cited, ...], Field(min_length=1)]  # no evidence, no claim


class CheckEvidence(_Row):
    check: CheckName
    status: CheckStatus
    reason: str | None


class ClaimEvidence(_Row):
    claim_id: str
    claim_type: ClaimType
    spoken: bool  # whether the card said it, or Selection kept it and the lens left it unsaid
    operands: tuple[OperandEvidence, ...]
    backing: CitedReading | None  # an interpretive claim's reading
    threshold: float | None  # the z its wording implies, for an interpretive claim
    verdict: Verdict
    checks: tuple[CheckEvidence, ...]
    recounted: tuple[float, ...]  # the verifier's own count of each operand's value
    model: str
    model_version: str


def drawer(
    claims: Sequence[Claim],
    spoken_ids: Collection[str],
    verifications: Sequence[Verification],
    record: Record,
    names: Mapping[str, str],
) -> tuple[ClaimEvidence, ...]:
    """The drawer for a card whose rendition kept `claims`, of which `spoken_ids` were said.

    Every claim here passed Verification, so each has a verification and every row it cites
    resolves; a claim that did not is a bug upstream, and raises rather than showing less.
    """
    by_claim = {check.claim_id: check for check in verifications}
    return tuple(
        _claim(claim, claim.claim_id in spoken_ids, by_claim[claim.claim_id], record, names)
        for claim in claims
    )


def _claim(
    claim: Claim,
    spoken: bool,
    verification: Verification,
    record: Record,
    names: Mapping[str, str],
) -> ClaimEvidence:
    backing = claim.backing_reading
    return ClaimEvidence(
        claim_id=claim.claim_id,
        claim_type=claim.claim_type,
        spoken=spoken,
        operands=tuple(_operand(operand, record, names) for operand in claim.operands),
        backing=None if backing is None else _reading(backing.id, record, names),
        threshold=claim.threshold,
        verdict=verification.verdict,
        checks=tuple(
            CheckEvidence(
                check=name,
                status=verification.checks[name].status,
                reason=verification.checks[name].reason,
            )
            for name in CheckName
        ),
        recounted=verification.recomputed_value,
        model=claim.model,
        model_version=claim.model_version,
    )


def _operand(operand: Operand, record: Record, names: Mapping[str, str]) -> OperandEvidence:
    return OperandEvidence(
        subject=names[operand.subject.id],
        metric=operand.metric,
        value=operand.value,
        window=operand.window,
        cited=tuple(_cited(ref, record, names) for ref in operand.evidence_ids),
    )


def _cited(ref: Ref, record: Record, names: Mapping[str, str]) -> CitedEvent | CitedReading:
    if ref.kind is RefKind.EVENT:
        return _event(ref.id, record, names)
    if ref.kind is RefKind.READING:
        return _reading(ref.id, record, names)
    raise ValueError(f"the drawer shows events and readings; {ref.kind} is not built in v1")


def _event(event_id: str, record: Record, names: Mapping[str, str]) -> CitedEvent:
    event = record.event[event_id]
    return CitedEvent(
        event_id=event.event_id,
        clock_ms=event.clock_ms,
        period=event.period,
        action=event.action,
        team=None if event.team is None else names[event.team],
        player=None if event.player is None else names[event.player],
        outcome=event.outcome,
    )


def _reading(reading_id: str, record: Record, names: Mapping[str, str]) -> CitedReading:
    reading = record.reading[reading_id]
    return CitedReading(
        reading_id=reading.reading_id,
        signal=reading.signal,
        team=names[reading.team],
        clock_ms=reading.clock_ms,
        window_ms=reading.window_ms,
        value=reading.value,
        baseline=reading.baseline,
        z_match=reading.z_match,
    )
