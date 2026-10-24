"""What crosses the bus from Rendering to Delivery.

`Card` is a stream message, like `MatchState`: sent, never stored. It pairs a rendition with the
match clock it describes, which the release rule needs (`display_at_clock`, invariant 8) and the
page shows on the card. `Rendition` itself carries no clock.

It also carries what Catch-up needs to summarise it later without the moment or the claims,
which Delivery does not hold: the moment's type and importance, and the body written with every
claim Selection kept (D4). The page reads none of these.

And it carries the card's overlay packet (D5), which Rendering writes and Delivery releases with
the card, never ahead of it.
"""

from pydantic import BaseModel, ConfigDict

from matchlens.models import ClockMs, MomentType, OverlayPacket, Rendition


class Card(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rendition: Rendition
    display_at_clock: ClockMs  # match clock, never wall clock
    moment_type: MomentType
    importance: float
    body_in_full: str  # `rendering.in_full`: the body with every selected claim spoken
    overlay: OverlayPacket
