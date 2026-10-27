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
OPPONENT = Ref(kind=RefKind.TEAM, id="side-b")
NAMES = {"side-a": "Larkfield", "side-b": "Ashworth"}
EMITTED = (MomentType.GOAL, MomentType.CHANCE, MomentType.TACTICAL_SHIFT)


def _lens(depth: Depth, **changes) -> Lens:
    lens = next(lens for lens in lenses.all_lenses() if lens.depth is depth)
    return lens.model_copy(update=changes)


CASUAL, ANALYST = _lens(Depth.CASUAL), _lens(Depth.ANALYST)
TEAM = _lens(Depth.ENGAGED, focus_team=SIDE.id)


def _moment(type_: MomentType = MomentType.GOAL, subject: Ref = SIDE) -> Moment:
    return Moment(
        moment_id="m", clock_ms=2_052_000, type=type_, subject=subject, importance=0.9,
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
    assert not re.search(r"\d", texts[Depth.CASUAL])


def test_every_emitted_moment_type_has_a_template_at_every_depth():
    for type_ in EMITTED:
        for depth in Depth:
            assert templates.lookup("en", type_, depth) is not None


# --- the team lens: supporter-oriented, neutral in voice (D31) ----------------------------------


def test_every_emitted_moment_type_has_a_sided_template_at_every_depth():
    for type_ in EMITTED:
        for depth in Depth:
            for side in templates.SIDES:
                assert templates.lookup("en", type_, depth, side) is not None


@pytest.mark.parametrize("type_", EMITTED)
def test_the_team_lens_tells_a_moment_for_and_against_its_side_differently(type_):
    ours = _text(render(_moment(type_, SIDE), _selected(), TEAM, NAMES))
    theirs = _text(render(_moment(type_, OPPONENT), _selected(), TEAM, NAMES))
    assert ours != theirs
    assert "Larkfield" in ours and "Larkfield" in theirs  # the focus side is in every card
    assert "Ashworth" in theirs


@pytest.mark.parametrize("type_", EMITTED)
@pytest.mark.parametrize("subject", [SIDE, OPPONENT])
def test_the_team_lens_is_partisan_in_emphasis_and_never_in_voice(type_, subject):
    for depth in Depth:
        lens = TEAM.model_copy(update={"depth": depth})
        text = _text(render(_moment(type_, subject), _selected(), lens, NAMES))
        assert not re.search(r"\b(we|our|us|ours)\b", text, re.I), text


def test_the_team_lens_reads_from_whichever_side_it_is_pointed_at():
    other = TEAM.model_copy(update={"focus_team": OPPONENT.id})
    moment = _moment(MomentType.GOAL, SIDE)
    assert _text(render(moment, _selected(), TEAM, NAMES)) != _text(
        render(moment, _selected(), other, NAMES)
    )


def _score(scorer: Ref, scorer_goals: float, against: Ref, against_goals: float) -> Claim:
    def operand(team: Ref, value: float) -> Operand:
        return Operand(
            subject=team, metric=Metric.GOALS, window=Window(start_ms=0, end_ms=2_052_000),
            value=value, evidence_ids=(Ref(kind=RefKind.EVENT, id="ev"),),
        )  # fmt: skip

    return Claim(
        claim_id="score", moment_id="m", claim_type=ClaimType.COMPARATIVE,
        operands=(operand(scorer, scorer_goals), operand(against, against_goals)),
        backing_reading=None, threshold=None, model="m", model_version="v",
    )  # fmt: skip


def test_an_opponent_lead_is_told_as_the_focus_side_trailing():
    claim = _score(OPPONENT, 2, SIDE, 1)
    text = _text(render(_moment(MomentType.GOAL, OPPONENT), _selected(claim), TEAM, NAMES))
    assert "Larkfield trail 2–1." in text
    match = _text(render(_moment(MomentType.GOAL, OPPONENT), _selected(claim), ANALYST, NAMES))
    assert "Ashworth lead 2–1." in match  # a match lens hears it from the side that scored


def test_reading_from_the_focus_side_leaves_the_claim_as_it_was_made():
    claim = _score(OPPONENT, 2, SIDE, 1)
    before = claim.model_dump()
    render(_moment(MomentType.GOAL, OPPONENT), _selected(claim), TEAM, NAMES)
    assert claim.model_dump() == before


def test_the_team_lens_speaks_where_the_moment_leaves_its_side_first():
    """Q28: B. One spoken claim, and for a team lens it is the score, not the explainer's first."""
    first, score = _claim("goals", value=2, metric=Metric.GOALS), _score(OPPONENT, 2, SIDE, 1)
    assert TEAM.detail_level is DetailLevel.FULL  # a supporter is told who as well as the score
    goal = _moment(MomentType.GOAL, OPPONENT)
    team = render(goal, _selected(first, score), TEAM, NAMES)
    assert "Larkfield trail 2–1." in _text(team)
    assert "goal for Larkfield" not in _text(team)
    assert team.surviving_claim_ids == ("goals", "score")  # the order spoken, not the order kept
    # A match lens has no side to leave first, and the scoreboard already shows the score, so it
    # hears the score last: the explainer's first claim is what it hears.
    match = ANALYST.model_copy(update={"detail_level": DetailLevel.STANDARD})
    assert "Ashworth 2" not in _text(render(goal, _selected(first, score), match, NAMES))


def test_a_side_lens_speaks_only_where_the_side_stands():
    """A supporter is told the score a goal left. A comparison that is not the score, and the
    count of the team's goals, are kept for the lens (Selection decided) but not spoken: how a
    goal came about is for the lenses that want the mechanism."""
    first = _claim("first", value=2, metric=Metric.GOALS)
    ours = _claim("t", value=0.7, metric=Metric.TERRITORY).operands[0]
    theirs = ours.model_copy(update={"subject": OPPONENT, "value": 0.3})
    territory = _claim("t", metric=Metric.TERRITORY).model_copy(
        update={"claim_type": ClaimType.COMPARATIVE, "operands": (ours, theirs)}
    )
    team = render(_moment(MomentType.GOAL), _selected(first, territory), TEAM, NAMES)
    assert "second goal" not in _text(team)
    assert team.surviving_claim_ids == ("first", "t")
    # A lens that follows no side hears the claims in the explainer's order (Q39).
    match = ANALYST.model_copy(update={"detail_level": DetailLevel.STANDARD})
    assert "goals so far: 2" in _text(
        render(_moment(MomentType.GOAL), _selected(first), match, NAMES)
    )


def test_a_comparison_with_the_sides_own_earlier_self_is_not_the_standing_either():
    earlier = _claim("earlier", value=0.6, metric=Metric.POSSESSION_CONTROL)
    earlier = earlier.model_copy(
        update={"claim_type": ClaimType.COMPARATIVE, "operands": (earlier.operands[0],) * 2}
    )
    first = _claim("first", value=2, metric=Metric.GOALS)
    text = _text(render(_moment(MomentType.GOAL), _selected(first, earlier), TEAM, NAMES))
    assert "second goal" not in text and "more of the ball" not in text


def test_an_unsided_template_cannot_name_the_focus_team(tmp_path):
    data = json.loads(templates.TEMPLATES_PATH.read_text())
    data["headlines"][0]["body"] = "{focus} have scored."
    path = tmp_path / "templates.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="focus"):
        templates.load(path)


def test_templates_are_keyed_on_depth_not_on_the_lens():
    renamed = ANALYST.model_copy(update={"lens_id": "something_else", "name": "Other"})
    a = render(_moment(), _selected(), ANALYST, NAMES)
    b = render(_moment(), _selected(), renamed, NAMES)
    assert (a.headline, a.body) == (b.headline, b.body)
    assert b.lens_id == "something_else"


# --- only what Selection selected, only what a claim says ---------------------------------------


def test_a_claim_selection_filtered_out_is_not_in_the_text():
    kept = _claim("kept", value=11, metric=Metric.BUILD_UP_PASSES)
    filtered = _claim(
        "filtered", value=777, metric=Metric.BUILD_UP_PASSES, claim_type=ClaimType.INTERPRETIVE
    )
    lens = ANALYST.model_copy(update={"allowed_claim_types": (ClaimType.DESCRIPTIVE,)})
    chosen = select(_moment(), [kept, filtered], lens, ShownCards())
    rendition = render(_moment(), chosen, lens, NAMES)
    assert "11" in _text(rendition)
    assert "777" not in _text(rendition)
    assert rendition.surviving_claim_ids == ("kept",)


def test_detail_level_decides_how_many_selected_claims_are_spoken():
    claims = (
        _claim("a", value=11, metric=Metric.BUILD_UP_PASSES),
        _claim("b", value=22, metric=Metric.BUILD_UP_PASSES),
    )

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
    claim = _claim(value=2.5, metric=Metric.BUILD_UP_PASSES)
    text = _text(render(_moment(), _selected(claim), ANALYST, NAMES))
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


# --- the score a goal leaves ---------------------------------------------------------------------

# The casual lens's detail, read at the engaged depth: a match lens that says figures.
NEUTRAL_ENGAGED = CASUAL.model_copy(update={"depth": Depth.ENGAGED})


def test_a_goal_card_says_the_score_it_left_in_words_to_casual_and_in_figures_otherwise():
    goal, score = _moment(MomentType.GOAL, SIDE), _score(SIDE, 2, OPPONENT, 1)
    casual = _text(render(goal, _selected(_claim(), score), CASUAL, NAMES))
    assert "Larkfield are one goal up." in casual
    assert not re.search(r"\d", casual)  # L3: casual says no number
    engaged = _text(render(goal, _selected(_claim(), score), NEUTRAL_ENGAGED, NAMES))
    assert "Larkfield lead 2–1." in engaged


def test_a_goal_against_the_focus_side_says_it_trails_leader_first():
    goal, score = _moment(MomentType.GOAL, OPPONENT), _score(OPPONENT, 2, SIDE, 0)
    selected = _selected(_claim(), score.model_copy(update={"operands": score.operands[:1]}))
    text = _text(render(goal, selected, CASUAL.model_copy(update={"focus_team": SIDE.id}), NAMES))
    assert "Larkfield are two goals down." in text


def test_the_score_is_said_once_when_a_spoken_claim_already_says_it():
    goal, score = _moment(MomentType.GOAL, OPPONENT), _score(OPPONENT, 2, SIDE, 1)
    text = _text(render(goal, _selected(score), TEAM, NAMES))
    assert text.count("2–1") == 1


def test_a_goal_with_no_score_claim_says_no_score():
    text = _text(render(_moment(MomentType.GOAL, SIDE), _selected(), NEUTRAL_ENGAGED, NAMES))
    assert "lead" not in text and "Level" not in text


def test_a_ruled_out_goal_that_had_put_its_side_ahead_is_told_as_a_cancelled_lead():
    ruled_out, score = _moment(MomentType.GOAL_DISALLOWED, SIDE), _score(SIDE, 2, OPPONENT, 2)
    casual = render(ruled_out, _selected(_claim(), score), CASUAL, NAMES)
    assert casual.headline == "Larkfield's lead is cancelled"
    assert casual.body is not None and "Level again." in casual.body
    engaged = render(ruled_out, _selected(_claim(), score), NEUTRAL_ENGAGED, NAMES)
    assert engaged.body is not None and "Back to 2–2." in engaged.body


def test_a_ruled_out_equaliser_is_told_as_one_and_from_the_side_still_behind():
    ruled_out, score = _moment(MomentType.GOAL_DISALLOWED, SIDE), _score(SIDE, 1, OPPONENT, 2)
    rendition = render(ruled_out, _selected(_claim(), score), NEUTRAL_ENGAGED, NAMES)
    assert rendition.headline == "VAR rules out Larkfield's equaliser"
    assert rendition.body is not None and rendition.body.startswith("Larkfield still trail 2–1.")


def test_a_ruled_out_goal_against_the_focus_side_is_told_from_that_side():
    ruled_out, score = _moment(MomentType.GOAL_DISALLOWED, OPPONENT), _score(OPPONENT, 1, SIDE, 1)
    rendition = render(ruled_out, _selected(_claim(), score), TEAM, NAMES)
    assert rendition.headline == "Larkfield level again as VAR rules it out"


def test_a_ruled_out_goal_names_the_clock_of_the_goal_it_took_away():
    scorer = Ref(kind=RefKind.PLAYER, id="p9")
    claim = Claim(
        claim_id="var", moment_id="m", claim_type=ClaimType.DESCRIPTIVE,
        operands=(Operand(
            subject=scorer, metric=Metric.RULED_OUT_OFFSIDE,
            window=Window(start_ms=5_051_000, end_ms=5_121_000), value=1.0,
            evidence_ids=(Ref(kind=RefKind.EVENT, id="goal"), Ref(kind=RefKind.EVENT, id="var")),
        ),),
        backing_reading=None, threshold=None, model="m", model_version="v",
    )  # fmt: skip
    names = NAMES | {"p9": "Tom Brack"}
    ruled_out = _moment(MomentType.GOAL_DISALLOWED, SIDE)
    analyst = render(ruled_out, _selected(claim), ANALYST, names)
    assert analyst.body is not None and "Tom Brack's goal at 84:11" in analyst.body
    casual = render(ruled_out, _selected(claim), CASUAL, names)
    assert not re.search(r"\d", f"{casual.headline} {casual.body}")


# --- each lens leads with its viewer's question ---------------------------------------------------


def test_a_match_lens_hears_the_score_from_the_side_that_scored():
    # "Larkfield pull one back. Larkfield are one goal down", not "Ashworth are one goal up".
    goal, score = _moment(MomentType.GOAL, SIDE), _score(SIDE, 1, OPPONENT, 2)
    casual = render(goal, _selected(_claim(), score), CASUAL, NAMES)
    assert casual.body is not None and casual.body.startswith("Larkfield are one goal down.")
    engaged = render(goal, _selected(_claim(), score), NEUTRAL_ENGAGED, NAMES)
    assert engaged.body is not None and engaged.body.startswith("Larkfield trail 2–1.")


def test_the_analyst_hears_how_a_goal_came_about_before_the_score():
    goal, score = _moment(MomentType.GOAL, SIDE), _score(SIDE, 2, OPPONENT, 1)
    analyst = render(goal, _selected(_claim(), score), ANALYST, NAMES)
    assert analyst.body == "A high-quality chance. Larkfield lead 2–1."
    casual = render(goal, _selected(_claim(), score), NEUTRAL_ENGAGED, NAMES)
    assert casual.body is not None and casual.body.startswith("Larkfield lead 2–1.")


def _saved_by(keeper: str = "k1") -> Claim:
    operand = Operand(
        subject=Ref(kind=RefKind.PLAYER, id=keeper), metric=Metric.SHOT_SAVED_BY,
        window=Window(start_ms=2_052_000, end_ms=2_052_000), value=1.0,
        evidence_ids=(Ref(kind=RefKind.EVENT, id="ev"),),
    )  # fmt: skip
    return Claim(
        claim_id="saved", moment_id="m", claim_type=ClaimType.DESCRIPTIVE, operands=(operand,),
        backing_reading=None, threshold=None, model="m", model_version="v",
    )  # fmt: skip


def test_a_save_closes_a_chance_card_for_every_viewer():
    names = NAMES | {"k1": "Dale Drustow"}
    chance = _moment(MomentType.CHANCE, SIDE)
    analyst = render(chance, _selected(_saved_by(), _claim()), ANALYST, names)
    assert analyst.body is not None and analyst.body.endswith("Saved by Dale Drustow.")
    assert analyst.body.startswith("A high-quality chance.")
    casual = render(chance, _selected(_saved_by(), _claim()), CASUAL, names)
    assert casual.body is not None and casual.body.endswith("Saved by Dale Drustow.")


def test_a_supporter_hears_a_shift_by_the_other_side_as_against_their_own():
    operand = Operand(
        subject=OPPONENT, metric=Metric.PRESSING_INTENSITY,
        window=Window(start_ms=1_752_000, end_ms=2_052_000), value=12.0,
        evidence_ids=(Ref(kind=RefKind.READING, id="r"),),
    )  # fmt: skip
    judged = Claim(
        claim_id="shift", moment_id="m", claim_type=ClaimType.INTERPRETIVE, operands=(operand,),
        backing_reading=Ref(kind=RefKind.READING, id="r"), threshold=2.0, model="m",
        model_version="v",
    )  # fmt: skip
    shift = _moment(MomentType.TACTICAL_SHIFT, OPPONENT)
    theirs = render(shift, _selected(judged), TEAM, NAMES)
    assert theirs.headline is not None and "against Larkfield" in theirs.headline.replace(
        "Against Larkfield", "against Larkfield"
    )
    neutral = render(shift, _selected(judged), NEUTRAL_ENGAGED, NAMES)
    assert neutral.headline is not None and "Larkfield" not in neutral.headline
