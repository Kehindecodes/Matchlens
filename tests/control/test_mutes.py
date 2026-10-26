"""P2: the mute circuit breaker (Q44: 1A, 2B, 3A, 4A).

A mute stops the cards that come after it, on one lens, and an unmute does not bring back what
was stopped. Every one of them is a `ProducerAction` on the record.
"""

import pytest

from matchlens import calltrace
from matchlens.control import AlreadyMuted, Mutes, NotMuted
from matchlens.models import ProducerActionType, Ref, RefKind

CASUAL = "match_casual"
ANALYST = "match_analyst"
MINUTE = 60_000


def _muted_from_ten_minutes(lens_id: str = CASUAL) -> Mutes:
    mutes = Mutes()
    mutes.mute(lens_id, 10 * MINUTE, "ops", "wrong player named")
    return mutes


def test_a_lens_is_muted_from_the_clock_it_was_muted_at_and_not_before():
    mutes = _muted_from_ten_minutes()
    assert not mutes.is_muted(CASUAL, 10 * MINUTE - 1)
    assert mutes.is_muted(CASUAL, 10 * MINUTE)
    assert mutes.is_muted(CASUAL, 90 * MINUTE)


def test_muting_one_lens_leaves_every_other_lens_alone():
    mutes = _muted_from_ten_minutes(CASUAL)
    assert mutes.is_muted(CASUAL, 20 * MINUTE)
    assert not mutes.is_muted(ANALYST, 20 * MINUTE)
    assert not mutes.stops(ANALYST, 20 * MINUTE)


def test_an_unmute_resumes_cards_from_that_clock_and_keeps_the_stopped_ones_stopped():
    mutes = _muted_from_ten_minutes()
    mutes.unmute(CASUAL, 20 * MINUTE, "ops", "fixed")
    assert mutes.is_muted(CASUAL, 15 * MINUTE)  # inside the mute: gone, and not back-filled
    assert not mutes.is_muted(CASUAL, 20 * MINUTE)  # from the unmute on: cards resume
    assert not mutes.is_muted(CASUAL, 25 * MINUTE)


def test_a_card_arriving_while_the_lens_is_muted_is_stopped_even_for_an_earlier_moment():
    # Q44: 2B. A card is published after its moment: one for 8:00 can arrive after a click at 10:00.
    mutes = _muted_from_ten_minutes()
    assert not mutes.is_muted(CASUAL, 8 * MINUTE)
    assert mutes.stops(CASUAL, 8 * MINUTE)


def test_a_card_from_inside_a_mute_that_arrives_after_the_unmute_is_still_stopped():
    mutes = _muted_from_ten_minutes()
    mutes.unmute(CASUAL, 20 * MINUTE, "ops", "fixed")
    assert mutes.stops(CASUAL, 15 * MINUTE)


def test_a_card_from_before_the_mute_that_arrives_after_the_unmute_goes_through():
    mutes = _muted_from_ten_minutes()
    mutes.unmute(CASUAL, 20 * MINUTE, "ops", "fixed")
    assert not mutes.stops(CASUAL, 8 * MINUTE)
    assert not mutes.stops(CASUAL, 21 * MINUTE)


def test_a_lens_can_be_muted_again_after_it_was_unmuted():
    mutes = _muted_from_ten_minutes()
    mutes.unmute(CASUAL, 20 * MINUTE, "ops", "fixed")
    mutes.mute(CASUAL, 30 * MINUTE, "ops", "again")
    assert not mutes.is_muted(CASUAL, 25 * MINUTE)
    assert mutes.is_muted(CASUAL, 15 * MINUTE)
    assert mutes.is_muted(CASUAL, 35 * MINUTE)


def test_every_mute_and_unmute_writes_a_producer_action_with_an_actor_and_a_reason():
    mutes = Mutes()
    mute = mutes.mute(CASUAL, 10 * MINUTE, "dana", "wrong player named")
    unmute = mutes.unmute(CASUAL, 20 * MINUTE, "dana", "fixed")

    assert mute.action is ProducerActionType.SUPPRESS
    assert unmute.action is ProducerActionType.RELEASE
    for action, clock, reason in (
        (mute, 10 * MINUTE, "wrong player named"),
        (unmute, 20 * MINUTE, "fixed"),
    ):
        assert action.target_id == Ref(kind=RefKind.LENS, id=CASUAL)
        assert action.actor == "dana"
        assert action.clock_ms == clock
        assert action.reason == reason
    assert mutes.actions() == [mute, unmute]
    assert mute.action_id != unmute.action_id


def test_muting_a_muted_lens_or_unmuting_one_that_is_not_muted_is_refused_and_logs_nothing():
    mutes = Mutes()
    with pytest.raises(NotMuted):
        mutes.unmute(CASUAL, MINUTE, "ops", "nothing to undo")
    mutes.mute(CASUAL, 10 * MINUTE, "ops", "first")
    with pytest.raises(AlreadyMuted):
        mutes.mute(CASUAL, 11 * MINUTE, "ops", "second")
    assert len(mutes.actions()) == 1
    assert mutes.is_muted(CASUAL, 10 * MINUTE + 1) and not mutes.is_muted(CASUAL, 10 * MINUTE - 1)


def test_the_mute_in_force_is_named_until_it_is_undone():
    mutes = Mutes()
    assert mutes.in_force(CASUAL) is None
    mute = mutes.mute(CASUAL, 10 * MINUTE, "ops", "wrong player named")
    assert mutes.in_force(CASUAL) == mute
    assert mutes.in_force(ANALYST) is None
    mutes.unmute(CASUAL, 20 * MINUTE, "ops", "fixed")
    assert mutes.in_force(CASUAL) is None


def test_control_is_entered_when_a_card_is_checked():
    mutes = Mutes()
    with calltrace.recording() as log:
        mutes.stops(CASUAL, MINUTE)
    assert "Control" in log
