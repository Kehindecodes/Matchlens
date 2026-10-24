"""An overlay packet for a test card, so the delivery tests can build a `Card` in one line."""

from matchlens.models import OverlayPacket, OverlayTemplate, Rendition


def overlay_for(rendition: Rendition, clock_ms: int) -> OverlayPacket:
    return OverlayPacket(
        packet_id=f"{rendition.rendition_id}:overlay",
        rendition_id=rendition.rendition_id,
        display_at_clock=clock_ms,
        duration_ms=5_000,
        template=OverlayTemplate.LOWER_THIRD,
        payload={"headline": rendition.headline or "", "body": rendition.body or ""},
    )
