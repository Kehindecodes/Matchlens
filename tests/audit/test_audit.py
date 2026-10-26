"""P3 (Q45: 1B): Audit keeps each moment's trail, append-only, for the views that read it.

What it keeps is what the pipeline already hands it: the moment, its claims, a verdict for each
claim, and a rendition for each lens. It holds no frame (invariant 1) and edits nothing
(invariant 2).
"""

import dataclasses

import pytest

from matchlens.audit import AlreadyRecorded, Audit, Unverified
from tests.audit.support import a_moment_with_claims, verify_all


def test_a_recorded_moment_is_kept_with_its_claims_and_verdicts(played):
    explained = a_moment_with_claims(played)
    verdicts = verify_all(explained)
    audit = Audit()

    audit.record(explained.moment, explained.claims, verdicts, ())

    [entry] = audit.trail()
    assert entry.moment == explained.moment
    assert entry.claims == tuple(explained.claims)
    assert entry.verifications == tuple(verdicts)
    assert entry.renditions == ()


def test_the_trail_is_in_the_order_moments_were_recorded(played):
    audit = Audit()
    moments = [explained for explained in played.explained if explained.claims][:4]
    for explained in moments:
        audit.record(explained.moment, explained.claims, verify_all(explained), ())

    assert [entry.moment.moment_id for entry in audit.trail()] == [
        explained.moment.moment_id for explained in moments
    ]


def test_a_reader_asks_only_for_what_came_after_what_it_has_seen(played):
    audit = Audit()
    moments = [explained for explained in played.explained if explained.claims][:4]
    for explained in moments:
        audit.record(explained.moment, explained.claims, verify_all(explained), ())

    later = audit.trail(after=2)

    assert [entry.moment.moment_id for entry in later] == [
        explained.moment.moment_id for explained in moments[2:]
    ]
    assert audit.trail(after=4) == ()


def test_a_moment_is_recorded_once_and_the_first_record_stands(played):
    explained = a_moment_with_claims(played)
    verdicts = verify_all(explained)
    audit = Audit()
    audit.record(explained.moment, explained.claims, verdicts, ())

    with pytest.raises(AlreadyRecorded):
        audit.record(explained.moment, explained.claims[:1], verdicts[:1], ())

    [entry] = audit.trail()
    assert entry.claims == tuple(explained.claims)


def test_a_claim_with_no_verdict_is_refused_rather_than_kept(played):
    # A claim without a verification counts as failed (invariant 5). Audit will not hold one that
    # looks as if nothing was ever said about it, so the trail cannot lose a rejection by omission.
    explained = a_moment_with_claims(played)
    verdicts = verify_all(explained)[:-1]
    audit = Audit()

    with pytest.raises(Unverified):
        audit.record(explained.moment, explained.claims, verdicts, ())

    assert audit.trail() == ()


def test_what_is_kept_cannot_be_edited(played):
    explained = a_moment_with_claims(played)
    audit = Audit()
    audit.record(explained.moment, explained.claims, verify_all(explained), ())

    [entry] = audit.trail()

    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.claims = ()  # type: ignore[misc]
    assert isinstance(entry.claims, tuple) and isinstance(entry.verifications, tuple)


def test_the_names_of_teams_and_players_are_kept_for_the_views_that_label_them():
    audit = Audit()
    assert audit.names == {}

    audit.introduce({"m-1-home": "Northfield", "m-1-home-p9": "A. Striker"})

    assert audit.names == {"m-1-home": "Northfield", "m-1-home-p9": "A. Striker"}
