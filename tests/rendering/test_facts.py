"""L7: D30's wording rules. Each phrase appears when its rule holds, and only then."""

import json
import re

import pytest

from matchlens.config import settings
from matchlens.models import Claim, ClaimType, Depth, Metric, Operand, Ref, RefKind, Window
from matchlens.rendering import templates
from matchlens.rendering.facts import sentence

HOME = Ref(kind=RefKind.TEAM, id="home")
AWAY = Ref(kind=RefKind.TEAM, id="away")
SCORER = Ref(kind=RefKind.PLAYER, id="home-p9")
NAMES = {"home": "Larkfield", "away": "Ostbridge", "home-p9": "Ada Quill"}


def _operand(
    metric: Metric, value: float, subject: Ref = HOME, start_ms: int = 600_000,
    end_ms: int = 600_000,
) -> Operand:  # fmt: skip
    return Operand(
        subject=subject, metric=metric, window=Window(start_ms=start_ms, end_ms=end_ms),
        value=value, evidence_ids=(Ref(kind=RefKind.EVENT, id="ev"),),
    )  # fmt: skip


def _claim(*operands: Operand, threshold: float | None = None) -> Claim:
    if threshold is not None:
        claim_type = ClaimType.INTERPRETIVE
    else:
        claim_type = ClaimType.COMPARATIVE if len(operands) == 2 else ClaimType.DESCRIPTIVE
    return Claim(
        claim_id="c", moment_id="m", claim_type=claim_type, operands=operands,
        backing_reading=Ref(kind=RefKind.READING, id="r") if threshold is not None else None,
        threshold=threshold, model="deterministic", model_version="claims-1",
    )  # fmt: skip


def _say(claim: Claim, depth: Depth = Depth.ENGAGED) -> str | None:
    return sentence(claim, depth, "en", NAMES)


def _said(claim: Claim, depth: Depth = Depth.ENGAGED) -> str:
    text = _say(claim, depth)
    assert text is not None, "this claim should be spoken"
    return text


# --- big chance, run of chances -------------------------------------------------------------------


def test_a_big_chance_is_the_spotters_chance_bar():
    bar = settings.spotter_chance_quality
    assert "big chance" in _said(_claim(_operand(Metric.SHOT_QUALITY, bar)))
    assert "hard chance" in _said(_claim(_operand(Metric.SHOT_QUALITY, bar - 0.01)))


def test_a_run_of_big_chances_is_spoken_from_the_third():
    run = settings.wording_chance_run
    end = settings.claim_chance_window_ms
    assert "third big chance" in _said(
        _claim(_operand(Metric.CHANCES, run, start_ms=0, end_ms=end))
    )
    assert _say(_claim(_operand(Metric.CHANCES, run - 1, start_ms=0, end_ms=end))) is None
    analyst = _said(_claim(_operand(Metric.CHANCES, run, start_ms=0, end_ms=end)), Depth.ANALYST)
    assert "in the last 10 minutes" in analyst


# --- the build-up --------------------------------------------------------------------------------


def _move(passes: int, seconds: int) -> Claim:
    return _claim(_operand(Metric.BUILD_UP_PASSES, passes, start_ms=0, end_ms=seconds * 1000))


def test_a_quick_attack_reaches_the_shot_inside_the_limit():
    limit_s = settings.wording_quick_attack_ms // 1000
    assert "quick attack" in _said(_move(3, limit_s))
    assert _say(_move(3, limit_s + 1)) is None


def test_a_patient_move_has_enough_passes():
    many = settings.wording_patient_passes
    assert "patient move" in _said(_move(many, 60))
    assert _say(_move(many - 1, 60)) is None


# --- goals ----------------------------------------------------------------------------------------


def test_the_scorer_is_named_and_a_second_goal_says_so():
    first = _said(_claim(_operand(Metric.GOALS, 1, subject=SCORER)))
    again = _said(_claim(_operand(Metric.GOALS, 2, subject=SCORER)))
    assert "Ada Quill" in first and "second" not in first
    assert "Ada Quill" in again and "second" in again
    assert "home-p9" not in first + again


@pytest.mark.parametrize(
    ("home", "away", "word"), [(2, 1, "lead"), (1, 1, "Level"), (1, 2, "trail")]
)
def test_the_score_is_said_only_with_both_sides_cited(home, away, word):
    claim = _claim(_operand(Metric.GOALS, home), _operand(Metric.GOALS, away, subject=AWAY))
    assert word in _said(claim)


def test_a_side_alone_on_goals_never_claims_a_lead():
    # The other side's nought cites nothing, so no claim asserts it (Q26 2a).
    text = _said(_claim(_operand(Metric.GOALS, 1)), Depth.CASUAL)
    assert "first goal" in text
    assert not re.search(r"\blead|front|behind|square\b", text)


# --- signals --------------------------------------------------------------------------------------


# Pressing intensity is passes allowed per defensive action: it rises when a side presses less.
@pytest.mark.parametrize(
    ("threshold", "phrase"),
    [(1.25, "pressing less"), (2.0, "pressing much less"),
     (-1.25, "pressing harder"), (-2.0, "pressing much harder")],
)  # fmt: skip
def test_the_signed_threshold_decides_the_direction_and_the_strength(threshold, phrase):
    claim = _claim(_operand(Metric.PRESSING_INTENSITY, 9.0), threshold=threshold)
    text = _said(claim, Depth.CASUAL)
    assert phrase in text
    if abs(threshold) < settings.claim_strong_z:
        assert "much" not in text


def test_a_comparison_with_earlier_names_the_boundary_and_one_with_the_opponent_names_them():
    now = _operand(Metric.POSSESSION_CONTROL, 0.62, start_ms=2_100_000, end_ms=2_400_000)
    before = _operand(Metric.POSSESSION_CONTROL, 0.41, start_ms=1_800_000, end_ms=2_100_000)
    theirs = _operand(Metric.POSSESSION_CONTROL, 0.38, subject=AWAY, end_ms=2_400_000)
    # The earlier window is a comparison, not a time: a card does not say when (26 Oct).
    assert "more of the ball than before." in _said(_claim(now, before))
    assert "more of the ball than Ostbridge" in _said(_claim(now, theirs))


def test_a_comparison_with_no_difference_says_nothing():
    same = _operand(Metric.TERRITORY, 0.5)
    assert _say(_claim(same, _operand(Metric.TERRITORY, 0.5, subject=AWAY))) is None


# --- the rows themselves --------------------------------------------------------------------------


def test_no_casual_fact_can_carry_a_number():
    data = json.loads(templates.TEMPLATES_PATH.read_text())
    for row in data["facts"]:
        if row["depth"] == "casual":
            assert templates.fields(row["text"]) <= templates.CASUAL_FACT_FIELDS, row
            assert not re.search(r"\d", row["text"]), row


def test_every_metric_has_words_at_every_depth():
    data = json.loads(templates.TEMPLATES_PATH.read_text())
    rows = {(r["metric"], r["depth"]) for r in data["facts"]}
    signals = {r["metric"] for r in data["signals"]}
    for metric in Metric:
        key = templates.SIGNAL_ROWS if metric.value in signals else metric.value
        for depth in Depth:
            assert (key, depth.value) in rows, (metric, depth)


# --- no calibrated value reaches a viewer ---------------------------------------------------------


@pytest.mark.parametrize("depth", list(Depth))
def test_a_shots_quality_is_said_in_words_and_never_as_its_value(depth):
    for value in (0.13, 0.41):
        text = _said(_claim(_operand(Metric.SHOT_QUALITY, value)), depth)
        assert "chance" in text and str(value) not in text


def test_an_interpretive_signal_claim_never_states_a_value_or_standard_deviations():
    claim = _claim(_operand(Metric.TERRITORY, 0.83), threshold=2.0)
    text = _said(claim, Depth.ANALYST)
    assert "playing much further up the pitch than earlier in this match" in text
    assert not re.search(r"\d", text) and "standard deviation" not in text


def test_a_chance_quality_comparison_is_said_without_a_number():
    ours = _operand(Metric.CHANCE_QUALITY, 1.42, end_ms=2_400_000)
    theirs = _operand(Metric.CHANCE_QUALITY, 0.04, subject=AWAY, end_ms=2_400_000)
    text = _said(_claim(ours, theirs), Depth.ANALYST)
    assert "creating better chances than" in text
    assert not re.search(r"\d", text)


def test_a_share_is_a_percentage_and_pressing_is_passes_per_defensive_action():
    ours = _operand(Metric.POSSESSION_CONTROL, 0.58, end_ms=2_400_000)
    theirs = _operand(Metric.POSSESSION_CONTROL, 0.42, subject=AWAY, end_ms=2_400_000)
    assert "Share of the passes:" in _said(_claim(ours, theirs), Depth.ANALYST)
    assert "58%" in _said(_claim(ours, theirs), Depth.ANALYST) and "42%" in _said(
        _claim(ours, theirs), Depth.ANALYST
    )
    ours = _operand(Metric.PRESSING_INTENSITY, 10.67, end_ms=2_400_000)
    theirs = _operand(Metric.PRESSING_INTENSITY, 8.0, subject=AWAY, end_ms=2_400_000)
    text = _said(_claim(ours, theirs), Depth.ANALYST)
    assert "opponent passes allowed per defensive action" in text.lower()
    assert "10.7" in text and "10.67" not in text


# --- the run set against the other side's ------------------------------------------------------


def test_a_chance_comparison_is_said_only_for_a_clear_edge_and_from_the_side_with_more():
    end = settings.claim_chance_window_ms
    ahead = _operand(Metric.CHANCES, 5, start_ms=0, end_ms=end)
    behind = _operand(Metric.CHANCES, 2, subject=AWAY, start_ms=0, end_ms=end)
    assert "lead the big chances 5 to 2" in _said(_claim(ahead, behind))
    assert "lead the big chances 5 to 2" in _said(_claim(behind, ahead))  # read from the leader
    assert "most of the chances" in _said(_claim(ahead, behind), Depth.CASUAL)
    close = _operand(Metric.CHANCES, 4, subject=AWAY, start_ms=0, end_ms=end)
    assert _say(_claim(ahead, close)) is None  # four to five is not an edge


def test_one_pass_is_not_passes():
    text = _said(_move(1, 6), Depth.ANALYST)
    assert "1 pass " in text and "passes" not in text


# --- how a goal came about ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("third", "casual", "analyst"),
    [
        (3, "high up the pitch", "final third"),
        (2, "in midfield", "midfield"),
        (1, "deep in their own half", "own third"),
    ],
)
def test_where_the_ball_was_won_is_said_in_words_and_in_thirds(third, casual, analyst):
    claim = _claim(_operand(Metric.BALL_WON_THIRD, third))
    assert casual in _said(claim, Depth.CASUAL)
    assert analyst in _said(claim, Depth.ANALYST)


def test_who_gave_the_ball_away_is_named():
    claim = _claim(_operand(Metric.BALL_LOST, 1, subject=SCORER))
    assert "Ada Quill" in _said(claim, Depth.CASUAL)
    assert "Ada Quill" in _said(claim, Depth.ANALYST)


def test_how_far_out_a_shot_was_is_said_in_bands_and_casual_hears_only_the_extremes():
    close, mid, far = (_claim(_operand(Metric.SHOT_DISTANCE, d)) for d in (8.4, 18.0, 27.5))
    assert "close range" in _said(close, Depth.CASUAL)
    assert _say(mid, Depth.CASUAL) is None  # nothing to say about a shot from about 18 metres
    assert "distance" in _said(far, Depth.CASUAL)
    for claim, metres in ((close, "8.4"), (mid, "18"), (far, "27.5")):
        assert f"{metres} m" in _said(claim, Depth.ANALYST)


# --- who, for a supporter ------------------------------------------------------------------------


def _said_from(claim: Claim, side: str, depth: Depth = Depth.ENGAGED) -> str:
    text = sentence(claim, depth, "en", NAMES, side=side)
    assert text is not None
    return text


def test_an_assist_a_save_and_a_block_name_the_player_and_never_the_position():
    names = {"home-p9": "Ada Quill"}
    assert "Ada Quill" in _said(_claim(_operand(Metric.ASSIST, 1, subject=SCORER)))
    keeper = _claim(_operand(Metric.BALL_LOST_BY_KEEPER, 1, subject=SCORER))
    for depth in Depth:
        said = _said(keeper, depth)
        assert "Ada Quill" in said
        assert not re.search(r"keeper|goalkeeper|GK", said, re.IGNORECASE), said
    assert names  # the mapping the pipeline supplies names players, not positions


def test_a_save_is_told_differently_to_the_side_that_shot_and_the_side_that_kept_it_out():
    saved = _claim(_operand(Metric.SHOT_SAVED_BY, 1, subject=SCORER))
    assert _said_from(saved, "for") == "Saved by Ada Quill."
    assert _said_from(saved, "against") == "Ada Quill makes the save."
    blocked = _claim(_operand(Metric.SHOT_BLOCKED_BY, 1, subject=SCORER))
    assert _said_from(blocked, "for") == "Blocked by Ada Quill."
    assert _said_from(blocked, "against") == "Ada Quill blocks it."


# --- how the attack was made --------------------------------------------------------------------


def test_a_switch_a_regain_a_combination_and_a_pressured_loss_are_said_without_a_cause():
    switch = _claim(_operand(Metric.SWITCH_OF_PLAY, 41.2))
    assert "switched across the pitch" in _said(switch, Depth.CASUAL)
    assert "41.2 m" in _said(switch, Depth.ANALYST)
    regain = _claim(_operand(Metric.REGAIN, 5.5, start_ms=100_000, end_ms=105_500))
    assert "straight back" in _said(regain, Depth.CASUAL)
    assert "within 6 seconds" in _said(regain, Depth.ENGAGED)
    assert "5.5 s" in _said(regain, Depth.ANALYST)
    combination = _claim(_operand(Metric.COMBINATION, 3, start_ms=100_000, end_ms=102_000))
    assert not re.search(r"\d", _said(combination, Depth.CASUAL))
    assert "3 players combined in 2 s before the shot" in _said(combination, Depth.ANALYST)
    pressed = _claim(_operand(Metric.PRESSURED_LOSS, 1, subject=SCORER))
    assert "Ada Quill gave it away under pressure" in _said(pressed, Depth.ENGAGED)
    for claim in (switch, regain, combination, pressed):
        assert not re.search(r"\bbecause\b", _said(claim, Depth.ANALYST))  # since, never because


# --- what the positions showed (Q48) --------------------------------------------------------------


def test_an_overload_sets_the_attackers_against_the_defenders_and_casual_hears_no_number():
    overload = _claim(_operand(Metric.OVERLOAD, 4), _operand(Metric.OVERLOAD, 1, subject=AWAY))
    assert _said(overload) == "Larkfield had 4 against 1 around the ball."
    assert "4 v 1" in _said(overload, Depth.ANALYST)
    assert not re.search(r"\d", _said(overload, Depth.CASUAL))


def test_a_decoy_run_and_an_early_run_name_the_runner_and_never_a_cause():
    decoy = _claim(_operand(Metric.DECOY_RUN, 14.3, subject=SCORER, start_ms=0, end_ms=3_500))
    early = _claim(_operand(Metric.EARLY_RUN, 9.1, subject=SCORER, start_ms=0, end_ms=1_500))
    for claim in (decoy, early):
        for depth in Depth:
            said = _said(claim, depth)
            assert said.startswith("Ada Quill") or "Ada Quill" in said
            # The frames show where everyone was, never why: no word claims space was made.
            assert not re.search(r"space|opened|created|dragged", said, re.IGNORECASE), said
        assert not re.search(r"\d", _said(claim, Depth.CASUAL))
    assert "14.3 m" in _said(decoy, Depth.ANALYST)
    assert "9.1 m in the 2 s" in _said(early, Depth.ANALYST)
