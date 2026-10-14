"""What crosses the bus from Rendering to Delivery.

`Card` is a stream message, like `MatchState`: sent, never stored. It pairs a rendition with the
match clock it describes, which the release rule needs (`display_at_clock`, invariant 8) and the
page shows on the card. `Rendition` itself carries no clock.
"""

from pydantic import BaseModel, ConfigDict

from matchlens.models import ClockMs, Rendition


class Card(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rendition: Rendition
    display_at_clock: ClockMs  # match clock, never wall clock
