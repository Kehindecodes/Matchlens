"""Group C: editorial output.

Everything upstream is a faithful record; everything here is a decision about what is worth
saying, and to whom. Every model is frozen: a correction is a new row, never an edit.

"""

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from matchlens.models.enums import MomentType, RefKind, SuppressionReason
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


class Claim(_Record):
    """One structured, checkable assertion. Schema pending Kehinde's design before A2."""


class Verification(_Record):
    """The record of checking one claim. Schema pending Kehinde's design with the six checks."""


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
