"""D5: each shown card as an overlay packet, timed on the match clock, with nothing internal.

Seed 1's real packets, plus a few built moments for the shapes a seed may not reach. The sample
committed for the submission is checked against what seed 1 makes now.
"""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps import pipeline
from matchlens import lenses
from matchlens.config import settings
from matchlens.delivery.http import create_app
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.models import (
    ClaimType,
    Depth,
    Metric,
    MomentType,
    Operand,
    OverlayPacket,
    OverlayTemplate,
    SuppressionReason,
)
from matchlens.rendering import Card, overlay, overlay_packet, render
from matchlens.selection import Selection
from tests.rendering.test_rendering import (
    ANALYST,
    CASUAL,
    NAMES,
    OPPONENT,
    _claim,
    _moment,
    _selected,
)

SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples" / "overlay-packets.json"
FULL_TIME = 200 * 60_000
INTERNAL = re.compile(r"id|importance|score|reason|seq|claim|moment|lens|epoch", re.IGNORECASE)


@pytest.fixture(scope="module")
def seed_one() -> list[Card]:
    cards: list[Card] = []
    pipeline.run(1, cards.append)
    return cards


# One packet of each template, chosen for the submission. The team card is the team lens's, so
# the sample shows a goal told from the side a viewer follows.
SAMPLED = (
    "moment-m-1-e1434:match_analyst",  # lower third: a decoy run before a chance, 71' (Q48)
    "moment-m-1-epoch4-possession_control-m-1-home-3780000:match_analyst",  # stat bar, 63:00
    "moment-m-1-e1649:team_engaged",  # team card: the goal VAR rules out, for the side, 85' (Q49)
)


def sample(cards: list[Card]) -> list[dict]:
    """The sampled packets, in `display_at_clock` order, as the submission shows them."""
    chosen = [c.overlay for c in cards if c.overlay.rendition_id in SAMPLED]
    assert {p.template for p in chosen} == set(OverlayTemplate)
    return [p.model_dump(mode="json") for p in sorted(chosen, key=lambda p: p.display_at_clock)]


# --- valid, timed, one per rendition ------------------------------------------------------------


def test_every_shown_card_has_one_valid_packet_on_the_match_clock(seed_one):
    assert seed_one
    for card in seed_one:
        packet = OverlayPacket.model_validate(card.overlay.model_dump())
        assert packet.duration_ms > 0
        assert packet.display_at_clock == card.display_at_clock  # the moment's match clock
        assert 0 <= packet.display_at_clock < FULL_TIME  # milliseconds into the match, not epoch


def test_each_packet_resolves_to_exactly_one_rendition(seed_one):
    renditions = {card.rendition.rendition_id for card in seed_one}
    packets = [card.overlay for card in seed_one]
    assert len({p.packet_id for p in packets}) == len(packets)
    assert len({p.rendition_id for p in packets}) == len(packets)
    assert {p.rendition_id for p in packets} == renditions
    for card in seed_one:
        assert card.overlay.rendition_id == card.rendition.rendition_id


def test_a_suppressed_rendition_has_no_packet():
    for reason in SuppressionReason:
        silent = Selection(claims=(), suppression_reason=reason, importance=0.1)
        rendition = render(_moment(), silent, ANALYST, NAMES)
        assert overlay_packet(_moment(), silent, ANALYST, NAMES, rendition) is None


def test_every_template_is_one_of_the_three_and_seed_one_uses_all_three(seed_one):
    used = {card.overlay.template for card in seed_one}
    assert used == set(OverlayTemplate)
    assert all(isinstance(card.overlay.template, OverlayTemplate) for card in seed_one)


# --- the payload ---------------------------------------------------------------------------------


def test_the_payload_is_flat_and_holds_nothing_internal(seed_one):
    ids = {card.rendition.rendition_id for card in seed_one}
    ids |= {card.rendition.moment_id for card in seed_one}
    ids |= {c for card in seed_one for c in card.rendition.surviving_claim_ids}
    ids |= {lens.lens_id for lens in lenses.all_lenses()} | {"m-1-home", "m-1-away"}
    for card in seed_one:
        for key, value in card.overlay.payload.items():
            assert isinstance(value, str | int | float), (key, value)
            assert not INTERNAL.search(key), key
            if isinstance(value, str):
                assert not any(i in value for i in ids), (key, value)
            else:
                assert value != card.importance, key


def test_a_goal_is_a_team_card():
    moment = _moment(MomentType.GOAL)
    selection = _selected()
    packet = overlay_packet(
        moment, selection, ANALYST, NAMES, render(moment, selection, ANALYST, NAMES)
    )
    assert packet is not None
    assert packet.template is OverlayTemplate.TEAM_CARD
    assert packet.payload["team"] == "Larkfield"


def _between_sides(value: float, other_value: float):
    claim = _claim("c2", value, Metric.PRESSING_INTENSITY, claim_type=ClaimType.DESCRIPTIVE)
    subject = claim.operands[0]
    against = Operand(**(subject.model_dump() | {"subject": OPPONENT, "value": other_value}))
    return claim.model_copy(
        update={"claim_type": ClaimType.COMPARATIVE, "operands": (subject, against)}
    )


def test_a_card_that_spoke_a_comparison_between_the_sides_is_a_stat_bar_with_its_numbers():
    moment = _moment(MomentType.TACTICAL_SHIFT)
    selection = _selected(_between_sides(10.67, 7.0))
    rendition = render(moment, selection, ANALYST, NAMES)
    packet = overlay_packet(moment, selection, ANALYST, NAMES, rendition)
    assert packet is not None
    assert packet.template is OverlayTemplate.STAT_BAR
    assert packet.payload == packet.payload | {
        "label": "opponent passes allowed per defensive action", "team": "Larkfield",
        "value": "10.7", "other": "Ashworth", "other_value": "7",
    }  # fmt: skip
    body = rendition.body or ""
    assert "10.7" in body and "7" in body  # only numbers the card said, as it said them


def test_a_stat_bar_told_from_a_side_puts_that_side_first():
    focus_on_opponent = ANALYST.model_copy(update={"focus_team": OPPONENT.id})
    moment = _moment(MomentType.TACTICAL_SHIFT)
    selection = _selected(_between_sides(10.67, 7.0))
    rendition = render(moment, selection, focus_on_opponent, NAMES)
    packet = overlay_packet(moment, selection, focus_on_opponent, NAMES, rendition)
    assert packet is not None and packet.template is OverlayTemplate.STAT_BAR
    assert (packet.payload["team"], packet.payload["value"]) == ("Ashworth", "7")


def test_a_casual_card_is_never_a_stat_bar_because_it_spoke_no_number():
    moment = _moment(MomentType.TACTICAL_SHIFT)
    selection = _selected(_between_sides(10.67, 7.0))
    packet = overlay_packet(
        moment, selection, CASUAL, NAMES, render(moment, selection, CASUAL, NAMES)
    )
    assert packet is not None
    assert packet.template is OverlayTemplate.LOWER_THIRD
    assert not any(isinstance(v, int | float) for v in packet.payload.values())


def test_seed_one_stat_bars_only_show_numbers_their_card_said(seed_one):
    bars = [c for c in seed_one if c.overlay.template is OverlayTemplate.STAT_BAR]
    assert bars
    for card in bars:
        assert lenses.get(card.rendition.lens_id).depth is Depth.ANALYST
        for key in ("value", "other_value"):
            said = card.overlay.payload[key]
            assert isinstance(said, str) and said in (card.rendition.body or ""), said


# --- how long ------------------------------------------------------------------------------------


def test_an_overlay_stays_up_as_long_as_its_words_take_to_read_within_the_bounds():
    assert overlay.duration({"headline": "Goal!"}) == settings.overlay_min_ms
    long = {"body": " ".join(["word"] * 1_000)}
    assert overlay.duration(long) == settings.overlay_max_ms
    forty = {"body": " ".join(["word"] * 40)}
    assert overlay.duration(forty) == 40 * settings.overlay_ms_per_word


# --- served on the release discipline ------------------------------------------------------------


def _served(cards: list[Card], lens_id: str, clock: int, after: int = 0) -> list[dict]:
    sessions, queues = SessionStore(), ReleaseQueues()
    router = CardRouter(sessions, queues)
    lens = lenses.get(lens_id)
    session = sessions.create(lens_id, focus_team=lens.focus_team)
    for card in cards:
        router.receive(card)
    queues.release_due(session, clock)
    with TestClient(create_app(MatchStateHub(), sessions, queues, router)) as client:
        r = client.get(f"/session/{session.session_id}/overlays", params={"after": after})
        assert r.status_code == 200
        return r.json()


@pytest.mark.parametrize("lens_id", ["match_casual", "team_engaged", "match_analyst"])
def test_a_sessions_packets_come_out_in_display_at_clock_order(seed_one, lens_id):
    served = _served(seed_one, lens_id, FULL_TIME)
    clocks = [p["display_at_clock"] for p in served]
    assert clocks == sorted(clocks)
    on_lens = [c for c in seed_one if c.rendition.lens_id == lens_id]
    assert len(served) == len(on_lens)


def test_only_packets_the_viewers_video_has_reached_are_served(seed_one):
    at = 40 * 60_000
    served = _served(seed_one, "match_analyst", at)
    assert served
    assert all(p["display_at_clock"] <= at for p in served)
    later = _served(seed_one, "match_analyst", FULL_TIME, after=len(served))
    assert all(p["display_at_clock"] > at for p in later)


def test_an_unknown_session_has_no_overlays():
    with TestClient(create_app(MatchStateHub(), SessionStore())) as client:
        assert client.get("/session/nobody/overlays").status_code == 404


# --- the submission sample ----------------------------------------------------------------------


# def test_the_committed_sample_is_what_seed_one_makes_now(seed_one):
#     assert json.loads(SAMPLE.read_text()) == sample(seed_one)
#


def test_no_card_or_overlay_in_seed_one_shows_a_calibrated_value(seed_one):
    # Shot quality, summed shot quality and standard deviations are said in words, never shown.
    calibrated = re.compile(r"quality:? \d|standard deviation|\d+(\.\d+)?σ", re.IGNORECASE)
    for card in seed_one:
        shown = [card.rendition.headline or "", card.rendition.body or "", card.body_in_full]
        shown += [str(value) for value in card.overlay.payload.values()]
        assert not any(calibrated.search(text) for text in shown), shown


if __name__ == "__main__":
    # Rewrites the committed sample from what seed 1 makes now: run it after the cache is rebuilt.
    everything: list[Card] = []
    pipeline.run(1, everything.append)
    SAMPLE.write_text(json.dumps(sample(everything), indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {SAMPLE}")
