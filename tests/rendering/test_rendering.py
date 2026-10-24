"""L3: template renditions. One selection in, one rendition out, no model.

Moments, claims and selections are constructed, because what is under test is how the words
follow from them. Lenses come from the registry by depth, so no test names a preset. The team
names are the pipeline's job to supply; here they are a plain mapping.
"""

import json
import re
from pathlib import Path

import pytest

from matchlens import calltrace, lenses
from matchlens.models import (
    Claim,
    ClaimType,
    Depth,
    DetailLevel,
    Lens,
    Metric,
    Moment,
    MomentType,
    Operand,
    Ref,
    RefKind,
    SuppressionReason,
    Window,
)
from matchlens.rendering import render, templates
from matchlens.selection import Selection, ShownCards, select

REPO_ROOT = Path(__file__).resolve().parents[2]
SIDE = Ref(kind=RefKind.TEAM, id="side-a")
NAMES = {"side-a": "Larkfield"}
EMITTED = (MomentType.GOAL, MomentType.CHANCE, MomentType.TACTICAL_SHIFT)


def _lens(depth: Depth, **changes) -> Lens:
    lens = next(lens for lens in lenses.all_lenses() if lens.depth is depth)
    return lens.model_copy(update=changes)


CASUAL, TEAM, ANALYST = _lens(Depth.CASUAL), _lens(Depth.ENGAGED), _lens(Depth.ANALYST)


def _moment(type_: MomentType = MomentType.GOAL) -> Moment:
    return Moment(
        moment_id="m", clock_ms=2_052_000, type=type_, subject=SIDE, importance=0.9,
        trigger_reading_ids=(), trigger_event_ids=("ev",), epoch_id="e", model="spotter",
        model_version="1",
    )  # fmt: skip


def _claim(
    claim_id: str = "c1",
    value: float = 0.41,
    metric: Metric = Metric.SHOT_QUALITY,
    end_ms: int = 2_052_000,
    claim_type: ClaimType = ClaimType.DESCRIPTIVE,
) -> Claim:
    operand = Operand(
        subject=SIDE, metric=metric, window=Window(start_ms=end_ms, end_ms=end_ms), value=value,
        evidence_ids=(Ref(kind=RefKind.EVENT, id="ev"),),
    )  # fmt: skip
    interpretive = claim_type is ClaimType.INTERPRETIVE
    return Claim(
        claim_id=claim_id, moment_id="m", claim_type=claim_type, operands=(operand,),
        backing_reading=Ref(kind=RefKind.READING, id="r") if interpretive else None,
        threshold=1.0 if interpretive else None, model="m", model_version="v",
    )  # fmt: skip


def _selected(*claims: Claim) -> Selection:
    return Selection(claims=claims or (_claim(),), suppression_reason=None, importance=0.9)


def _text(rendition) -> str:
    return f"{rendition.headline}\n{rendition.body}"


# --- three registers -----------------------------------------------------------------------------


@pytest.mark.parametrize("type_", EMITTED)
def test_the_same_moment_reads_differently_through_three_lenses(type_):
    texts = {
        depth: _text(render(_moment(type_), _selected(), lens, NAMES))
        for depth, lens in ((Depth.CASUAL, CASUAL), (Depth.ENGAGED, TEAM), (Depth.ANALYST, ANALYST))
    }
    assert len(set(texts.values())) == 3
    assert re.search(r"\d", texts[Depth.ANALYST])
    assert not re.search(r"\d", texts[Depth.CASUAL])


def test_every_emitted_moment_type_has_a_template_at_every_depth():
    for type_ in EMITTED:
        for depth in Depth:
            assert templates.lookup("en", type_, depth) is not None


def test_the_team_register_is_the_match_register_until_o3():
    """No supporter voice: the engaged text names the side and never says we, our or us."""
    for type_ in EMITTED:
        text = _text(render(_moment(type_), _selected(), TEAM, NAMES))
        assert "Larkfield" in text
        assert not re.search(r"\b(we|our|us)\b", text, re.I)


def test_templates_are_keyed_on_depth_not_on_the_lens():
    renamed = ANALYST.model_copy(update={"lens_id": "something_else", "name": "Other"})
    a = render(_moment(), _selected(), ANALYST, NAMES)
    b = render(_moment(), _selected(), renamed, NAMES)
    assert (a.headline, a.body) == (b.headline, b.body)
    assert b.lens_id == "something_else"


# --- only what Selection selected, only what a claim says ---------------------------------------


def test_a_claim_selection_filtered_out_is_not_in_the_text():
    kept = _claim("kept", value=11)
    filtered = _claim("filtered", value=777, claim_type=ClaimType.INTERPRETIVE)
    lens = ANALYST.model_copy(update={"allowed_claim_types": (ClaimType.DESCRIPTIVE,)})
    chosen = select(_moment(), [kept, filtered], lens, ShownCards())
    rendition = render(_moment(), chosen, lens, NAMES)
    assert "11" in _text(rendition)
    assert "777" not in _text(rendition)
    assert rendition.surviving_claim_ids == ("kept",)


def test_detail_level_decides_how_many_selected_claims_are_spoken():
    claims = (_claim("a", value=11), _claim("b", value=22))

    def spoken(level: DetailLevel) -> str:
        lens = ANALYST.model_copy(update={"detail_level": level})
        return _text(render(_moment(), _selected(*claims), lens, NAMES))

    minimal, standard, full = (spoken(level) for level in DetailLevel)
    assert "11" not in minimal and "22" not in minimal
    assert "11" in standard and "22" not in standard
    assert "11" in full and "22" in full


def test_every_surviving_claim_is_listed_even_when_detail_does_not_speak_it():
    claims = (_claim("a"), _claim("b"))
    rendition = render(_moment(), _selected(*claims), CASUAL, NAMES)
    assert rendition.surviving_claim_ids == ("a", "b")


def test_a_claim_the_wording_rules_have_no_form_for_says_nothing_extra():
    # Two big chances in ten minutes is not a run: D30 speaks a run from the third.
    quiet = _claim("quiet", value=2, metric=Metric.CHANCES)
    rendition = render(_moment(MomentType.CHANCE), _selected(quiet), ANALYST, NAMES)
    words = templates.lookup("en", MomentType.CHANCE, Depth.ANALYST)
    assert rendition.body == words.body.format(team="Larkfield", window="at 34:12")


def test_every_number_in_the_text_comes_from_a_claim():
    claim = _claim(value=37.0, end_ms=2_052_000)  # 34:12
    allowed = {"37", "34", "12"}
    for type_ in EMITTED:
        for lens in (CASUAL, TEAM, ANALYST):
            text = _text(render(_moment(type_), _selected(claim), lens, NAMES))
            assert set(re.findall(r"\d+", text)) <= allowed, text


def test_a_value_is_written_as_the_claim_holds_it():
    text = _text(render(_moment(), _selected(_claim(value=2.5)), ANALYST, NAMES))
    assert "2.5" in text


# --- deterministic -------------------------------------------------------------------------------


def test_the_same_inputs_make_byte_identical_text():
    def go():
        r = render(_moment(), _selected(_claim()), ANALYST, NAMES)
        return r.rendition_id, r.headline, r.body, r.surviving_claim_ids, r.language

    assert go() == go()


# --- silence is a record -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason", [SuppressionReason.BELOW_THRESHOLD, SuppressionReason.RATE_LIMITED]
)
def test_a_suppressed_selection_is_a_suppressed_rendition_with_selections_reason(reason):
    silent = Selection(claims=(), suppression_reason=reason, importance=0.1)
    rendition = render(_moment(), silent, CASUAL, NAMES)
    assert rendition.suppressed
    assert rendition.suppression_reason is reason
    assert rendition.headline is None and rendition.body is None
    assert rendition.surviving_claim_ids == ()


# --- the rest of the contract --------------------------------------------------------------------


def test_the_rendition_carries_the_lens_language():
    assert render(_moment(), _selected(), ANALYST, NAMES).language == ANALYST.language


def test_a_language_with_no_templates_is_an_error_not_a_guess():
    other = ANALYST.model_copy(update={"language": "fr"})
    with pytest.raises(LookupError):
        render(_moment(), _selected(), other, NAMES)


def test_a_team_with_no_name_is_an_error_not_an_id_on_a_viewers_screen():
    with pytest.raises(KeyError):
        render(_moment(), _selected(), CASUAL, {})


def test_rendering_is_traced_as_the_rendering_component():
    with calltrace.recording() as seen:
        render(_moment(), _selected(), CASUAL, NAMES)
    assert "Rendering" in seen


def test_a_template_may_only_use_fields_the_renderer_fills(tmp_path):
    bad = tmp_path / "t.json"
    bad.write_text(
        json.dumps(
            {
                "headlines": [
                    {
                        "language": "en",
                        "moment_type": "goal",
                        "depth": "casual",
                        "headline": "{score}",
                        "body": "b",
                    }
                ],
                "facts": [],
            }
        )
    )
    with pytest.raises(ValueError, match="score"):
        templates.load(bad)


def test_the_word_for_shot_quality_is_never_the_other_one():
    needle = "x" + "G"
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for root in ("matchlens/rendering", "tests/rendering")
        for path in (REPO_ROOT / root).rglob("*")
        if path.is_file() and path.suffix in {".py", ".json"} and needle in path.read_text()
    ]
    assert offenders == []
