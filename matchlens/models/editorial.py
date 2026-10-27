"""Group C: editorial output.

Everything upstream is a faithful record; everything here is a decision about what is worth
saying, and to whom. Every model is frozen: a correction is a new row, never an edit.

"""

from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from matchlens.models.enums import (
    CheckName,
    CheckStatus,
    ClaimType,
    Metric,
    MomentType,
    RefKind,
    SuppressionReason,
    Verdict,
)
from matchlens.models.match_record import ClockMs
from matchlens.models.refs import Ref

_SUBJECT_KINDS = frozenset({RefKind.TEAM, RefKind.PLAYER})


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Moment(_Record):
    """Something the spotter judged worth saying. Cites the readings and events that fired it."""

    moment_id: str
    clock_ms: ClockMs
    type: MomentType
    subject: Ref  # a team or a player
    importance: float
    trigger_reading_ids: tuple[str, ...]
    trigger_event_ids: tuple[str, ...]
    epoch_id: str
    model: str
    model_version: str

    @model_validator(mode="after")
    def _subject_is_a_team_or_player(self):
        if self.subject.kind not in _SUBJECT_KINDS:
            raise ValueError(f"a moment's subject is a team or a player, not {self.subject.kind}")
        return self

    @model_validator(mode="after")
    def _cites_what_fired_it(self):
        if not self.trigger_reading_ids and not self.trigger_event_ids:
            raise ValueError("a moment must cite at least one reading or event")
        return self


# A position reading is what the frames showed, measured by Understanding (Q48).
_EVIDENCE_KINDS = frozenset({RefKind.EVENT, RefKind.READING, RefKind.POSITION, RefKind.RUN})
# How many operands each claim type has (D21). The rule over them is the same for every type.
_OPERANDS = {ClaimType.DESCRIPTIVE: 1, ClaimType.COMPARATIVE: 2, ClaimType.INTERPRETIVE: 1}


class Window(_Record):
    """A stretch of match clock, `start_ms` to `end_ms`."""

    start_ms: ClockMs
    end_ms: ClockMs

    @model_validator(mode="after")
    def _start_is_not_after_end(self):
        if self.start_ms > self.end_ms:
            raise ValueError("a window cannot start after it ends")
        return self


class Operand(_Record):
    """One side of a claim: a measured value for one subject, over its own window and evidence.

    `metric` is one of D30's eight, each recountable from the rows `evidence_ids` cites.
    """

    subject: Ref  # a team or a player
    metric: Metric
    window: Window
    value: float
    evidence_ids: Annotated[tuple[Ref, ...], Field(min_length=1)]  # no evidence, no claim

    @model_validator(mode="after")
    def _subject_is_a_team_or_player(self):
        if self.subject.kind not in _SUBJECT_KINDS:
            raise ValueError(f"an operand's subject is a team or a player, not {self.subject.kind}")
        return self

    @model_validator(mode="after")
    def _evidence_is_events_readings_positions_or_runs(self):
        wrong = [r.kind for r in self.evidence_ids if r.kind not in _EVIDENCE_KINDS]
        if wrong:
            raise ValueError(
                f"evidence is events, readings, positions or runs, not {sorted(set(wrong))}"
            )
        return self


class Claim(_Record):
    """One structured, checkable assertion: one or two operands, never prose (D21).

    A descriptive claim has one operand and a comparative claim two, the subject and what it is
    compared against. An interpretive claim has one, plus the signal reading that backs it and
    the threshold its wording implies, so the judgement is a field rather than a word.
    """

    claim_id: str
    moment_id: str
    claim_type: ClaimType
    operands: tuple[Operand, ...]
    backing_reading: Ref | None  # iff interpretive
    threshold: float | None  # iff interpretive
    model: str
    model_version: str

    @model_validator(mode="after")
    def _operands_match_the_claim_type(self):
        expected = _OPERANDS[self.claim_type]
        if len(self.operands) != expected:
            raise ValueError(
                f"a {self.claim_type} claim has {expected} operand(s), not {len(self.operands)}"
            )
        return self

    @model_validator(mode="after")
    def _only_an_interpretive_claim_is_backed(self):
        interpretive = self.claim_type is ClaimType.INTERPRETIVE
        if interpretive != (self.backing_reading is not None):
            raise ValueError("backing_reading is required iff the claim is interpretive")
        if interpretive != (self.threshold is not None):
            raise ValueError("threshold is required iff the claim is interpretive")
        if self.backing_reading is not None and self.backing_reading.kind is not RefKind.READING:
            raise ValueError("an interpretive claim is backed by a signal reading")
        return self


class CheckResult(_Record):
    """The outcome of one check, and why when it failed."""

    status: CheckStatus
    reason: str | None = None

    @model_validator(mode="after")
    def _a_failure_says_why(self):
        if self.status is CheckStatus.FAILED and not self.reason:
            raise ValueError("a failed check needs a reason")
        return self


class Verification(_Record):
    """The record of checking one claim: one per claim, and a claim without one counts as failed."""

    verification_id: str
    claim_id: str
    verdict: Verdict
    checks: dict[CheckName, CheckResult]
    recomputed_value: tuple[float, ...]
    failure_reason: str | None
    latency_ms: Annotated[int, Field(ge=0)]  # wall time, so not ClockMs
    model: str  # whatever produced the verdict, e.g. the verifier
    model_version: str

    @model_validator(mode="after")
    def _all_six_checks_ran(self):
        missing = set(CheckName) - set(self.checks)
        if missing:
            raise ValueError(f"every check must run; missing {sorted(missing)}")
        return self

    @model_validator(mode="after")
    def _verdict_follows_the_checks(self):
        all_clear = all(r.status is not CheckStatus.FAILED for r in self.checks.values())
        if (self.verdict is Verdict.PASS) != all_clear:
            raise ValueError("verdict is pass iff no check failed")
        return self

    @model_validator(mode="after")
    def _a_failure_has_a_reason(self):
        if (self.verdict is Verdict.FAIL) != (self.failure_reason is not None):
            raise ValueError("failure_reason is required iff the verdict is fail")
        return self


class Rendition(_Record):
    """One moment as one lens presents it.

    A suppressed rendition is a record of silence, not an absence (invariant 11): it carries
    exactly one `suppression_reason` and nothing to show.
    """

    rendition_id: str
    moment_id: str
    lens_id: str
    language: str  # ISO 639-1
    headline: str | None
    body: str | None
    surviving_claim_ids: tuple[str, ...]
    suppressed: bool
    suppression_reason: SuppressionReason | None
    rendered_at: AwareDatetime
    model: str  # what wrote the words: the templates, or a model (A4)
    model_version: str

    @model_validator(mode="after")
    def _reason_iff_suppressed(self):
        if self.suppressed != (self.suppression_reason is not None):
            raise ValueError("suppression_reason is required iff suppressed, null otherwise")
        return self

    @model_validator(mode="after")
    def _silence_shows_nothing(self):
        shown = (self.headline, self.body)
        if self.suppressed:
            if any(v is not None for v in shown) or self.surviving_claim_ids:
                raise ValueError("a suppressed rendition has no headline, body or claims")
        elif any(v is None for v in shown):
            raise ValueError("a rendition that is shown needs a headline and a body")
        return self
