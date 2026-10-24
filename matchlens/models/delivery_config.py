"""Group D: delivery and configuration.

A lens is data, never code (invariant 10): adding one is inserting a `Lens` row. A viewer is a
session holding preferences, not a user account. Every model is frozen; a session that moves
on is replaced with an updated copy.
"""

from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from matchlens.models.enums import (
    ClaimType,
    Depth,
    DetailLevel,
    MomentType,
    OverlayTemplate,
    ProducerActionType,
    RefKind,
    Scope,
)
from matchlens.models.match_record import ClockMs
from matchlens.models.refs import Ref

_ACTION_TARGET_KINDS = frozenset({RefKind.MOMENT, RefKind.RENDITION, RefKind.LENS})


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Lens(_Record):
    """One viewing experience, as a point on the scope and depth axes."""

    lens_id: str
    name: str
    audience: str
    scope: Scope
    breakthrough_types: tuple[MomentType, ...]  # bypass the scope filter, still rendered through it
    depth: Depth
    importance_threshold: float
    max_cards_per_10min: Annotated[int, Field(ge=0)]
    allowed_claim_types: tuple[ClaimType, ...]
    detail_level: DetailLevel
    language: str  # ISO 639-1
    focus_team: str | None
    focus_player: str | None  # unused in v1

    @model_validator(mode="after")
    def _focus_matches_the_scope(self):
        if (self.scope is Scope.TEAM) != (self.focus_team is not None):
            raise ValueError("focus_team is required iff scope is team, null otherwise")
        if (self.scope is Scope.PLAYER) != (self.focus_player is not None):
            raise ValueError("focus_player is required iff scope is player, null otherwise")
        return self


class ViewerSession(_Record):
    """One person watching.

    `focus_team` mirrors the lens rule (required iff the lens is team scope), but the session
    does not carry the scope, so that rule is checked where the session meets its lens.
    """

    session_id: str
    lens_id: str
    language: str  # ISO 639-1
    joined_at: AwareDatetime
    focus_team: str | None
    focus_player: str | None  # unused in v1
    last_seen_clock: ClockMs | None  # None until the first card is released
    stream_offset_ms: ClockMs  # how far this viewer's video lags the action (D7)


class ProducerAction(_Record):
    """What a producer did. The producer is a role, not an entity."""

    action_id: str
    target_id: Ref  # a moment, a rendition or a lens
    action: ProducerActionType
    actor: str
    clock_ms: ClockMs
    reason: str | None

    @model_validator(mode="after")
    def _target_is_actionable(self):
        if self.target_id.kind not in _ACTION_TARGET_KINDS:
            raise ValueError(
                f"a producer action targets a moment, rendition or lens, not {self.target_id.kind}"
            )
        return self


class OverlayPacket(_Record):
    """A rendition formatted for a streaming player to render over the picture (D34).

    Client-side and per session, which is what keeps it personalized — a broadcast graphics system
    would render one overlay for everyone on the feed.
    """

    packet_id: str
    rendition_id: str
    display_at_clock: ClockMs  # match clock, never wall clock
    duration_ms: Annotated[int, Field(gt=0)]
    template: OverlayTemplate
    payload: dict[str, str | int | float]
