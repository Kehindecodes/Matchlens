"""What crosses the bus to the producer view, beside `Card` (P1, Q43: 1A).

A `Card` is only what a viewer is given, so a lens that said nothing leaves no trace on it.
These are the other half: for one moment, what each lens did with it, including the suppressed
renditions (invariant 11) and what Selection judged. Like `Card` they are sent, never stored,
and no viewer is ever sent one.

A lens that was meant to answer and has no `LensOutcome` has failed. That is what tells it from
a lens that chose silence, which has an outcome whose rendition is suppressed.
"""

from pydantic import BaseModel, ConfigDict, model_validator

from matchlens.models import ClockMs, MomentType, Rendition


class LensOutcome(BaseModel):
    """One lens's side of one moment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lens_id: str
    rendition: Rendition  # shown or suppressed: either way a record
    importance: float  # what the lens judged the moment at, after its scope's reweight
    shown_in_window: int  # cards the lens showed in the ten match minutes to the moment's clock


class MomentOutcome(BaseModel):
    """What happened to one moment, lens by lens.

    `lens_ids` are the lenses that were meant to answer, so a missing outcome can be told from
    a lens that does not exist. `failure` names what stopped the moment, if something did.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    moment_id: str
    clock_ms: ClockMs
    moment_type: MomentType
    lens_ids: tuple[str, ...]
    outcomes: tuple[LensOutcome, ...]
    failure: str | None = None

    @model_validator(mode="after")
    def _outcomes_are_for_lenses_that_were_meant_to_answer(self):
        answered = [outcome.lens_id for outcome in self.outcomes]
        if len(set(answered)) != len(answered):
            raise ValueError("a lens answers a moment once")
        unexpected = set(answered) - set(self.lens_ids)
        if unexpected:
            raise ValueError(f"outcomes for lenses that were not asked: {sorted(unexpected)}")
        return self
