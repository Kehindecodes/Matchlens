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
    assert "more of the ball than before 35:00" in _said(_claim(now, before))
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
    assert "playing much further up the pitch than their norm" in text
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
