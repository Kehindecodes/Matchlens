"""D5: the overlay sample read as a renderer outside MatchLens would, with a plain JSON parser.

No project import on purpose: if this needed MatchLens to make sense of a packet, the packet
would not be a contract. `tests/rendering/test_overlay.py` keeps the sample current.
"""

import json
from pathlib import Path

SAMPLE = Path(__file__).resolve().parents[1] / "docs" / "samples" / "overlay-packets.json"
TEMPLATES = {"lower_third", "stat_bar", "team_card"}
# What each template needs to be drawn, beyond the headline and the clock every packet has.
NEEDS = {
    "lower_third": {"body": str},
    "team_card": {"team": str, "body": str},
    "stat_bar": {"label": str, "team": str, "value": str, "other": str, "other_value": str},
}


def _packets() -> list[dict]:
    packets = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert isinstance(packets, list) and packets
    return packets


def test_every_packet_has_the_fields_a_renderer_schedules_by():
    for packet in _packets():
        assert isinstance(packet["display_at_clock"], int) and packet["display_at_clock"] >= 0
        assert isinstance(packet["duration_ms"], int) and packet["duration_ms"] > 0
        assert packet["template"] in TEMPLATES
        assert isinstance(packet["packet_id"], str) and isinstance(packet["rendition_id"], str)


def test_every_payload_is_flat_and_has_what_its_template_draws():
    for packet in _packets():
        payload = packet["payload"]
        assert all(isinstance(v, str | int | float) for v in payload.values())
        assert isinstance(payload["headline"], str) and isinstance(payload["clock"], str)
        for field, kind in NEEDS[packet["template"]].items():
            assert isinstance(payload[field], kind), (packet["template"], field)


def test_the_packets_are_in_clock_order_and_cover_every_template():
    packets = _packets()
    clocks = [p["display_at_clock"] for p in packets]
    assert clocks == sorted(clocks)
    assert {p["template"] for p in packets} == TEMPLATES
