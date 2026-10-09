import pytest
from pydantic import ValidationError

from matchlens.models import (
    Action,
    BodyPart,
    Outcome,
    Phase,
    Ref,
    RefKind,
)


def test_group_a_enum_values_match_the_data_model():
    assert {p.value for p in Phase} == {"in_play", "stopped", "set_piece"}
    assert {b.value for b in BodyPart} == {"left_foot", "right_foot", "head", "other"}
    assert {a.value for a in Action} == {
        "pass", "carry", "shot", "tackle", "interception", "clearance", "block",
        "aerial_duel", "save", "foul", "throw_in", "corner", "goal_kick", "free_kick",
        "penalty",
    }  # fmt: skip
    assert {o.value for o in Outcome} == {
        "complete", "incomplete", "blocked", "goal", "saved", "off_target", "won", "lost",
        "out_of_play",
    }  # fmt: skip


def test_ref_kind_values_match_the_data_model():
    assert {k.value for k in RefKind} == {
        "team", "player", "event", "reading", "run", "moment", "rendition", "lens",
    }  # fmt: skip


def test_ref_carries_kind_and_id_and_round_trips():
    ref = Ref(kind=RefKind.EVENT, id="e-1")
    assert (ref.kind, ref.id) == (RefKind.EVENT, "e-1")
    assert Ref.model_validate_json(ref.model_dump_json()) == ref


def test_ref_accepts_kind_as_string_but_rejects_unknown_kind():
    assert Ref(kind="team", id="t-1").kind is RefKind.TEAM
    with pytest.raises(ValidationError):
        Ref(kind="stadium", id="x")


def test_ref_is_hashable_and_immutable():
    ref = Ref(kind=RefKind.PLAYER, id="p-1")
    assert {ref, Ref(kind=RefKind.PLAYER, id="p-1")} == {ref}
    with pytest.raises(ValidationError):
        ref.id = "p-2"
