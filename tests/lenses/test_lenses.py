"""L1: the three presets are rows in a committed file, and nothing in code knows their names.

The calibration test runs the demo match (seed 1, the default archetype) through Ingest,
Understanding and the Spotter, and compares how many of its moments each lens's threshold admits.
"""

import ast
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from matchlens import lenses
from matchlens.config import settings
from matchlens.ingest import Ingest
from matchlens.models import ClaimType, Depth, Lens, MomentType, Scope
from matchlens.source import MatchSetup, simulate
from matchlens.spotting import Spotter
from matchlens.understanding import Understanding

REPO_ROOT = Path(__file__).resolve().parents[2]
FOUR_LENSES = Path(__file__).with_name("fixtures") / "four_lenses.json"


def _lens_ids() -> set[str]:
    return {row["lens_id"] for row in json.loads(lenses.LENSES_PATH.read_text())["lenses"]}


def _by_depth() -> dict[Depth, Lens]:
    return {lens.depth: lens for lens in lenses.all_lenses()}


# --- the rows ------------------------------------------------------------------------------------


def test_there_are_three_lenses_and_the_registry_serves_them():
    all_ = lenses.all_lenses()
    assert len(all_) == 3
    assert {(lens.scope, lens.depth) for lens in all_} == {
        (Scope.MATCH, Depth.CASUAL),
        (Scope.MATCH, Depth.ANALYST),
        (Scope.TEAM, Depth.ENGAGED),
    }
    for lens in all_:
        assert lenses.get(lens.lens_id) == lens


def test_an_unknown_lens_is_a_key_error():
    with pytest.raises(KeyError):
        lenses.get("no_such_lens")


def test_the_default_lens_is_one_of_the_presets():
    assert lenses.get(settings.default_lens_id) in lenses.all_lenses()


def test_every_field_comes_from_the_data_file():
    rows = json.loads(lenses.LENSES_PATH.read_text())["lenses"]
    assert lenses.load() == [Lens.model_validate(row) for row in rows]
    assert set(Lens.model_fields) == set(rows[0])


def test_focus_team_is_named_for_the_team_lens_and_null_for_the_match_lenses():
    for lens in lenses.all_lenses():
        assert (lens.focus_team is not None) == (lens.scope is Scope.TEAM)
    demo_home = next(
        i for i in simulate(settings.match_seed) if isinstance(i, MatchSetup)
    ).match.teams[0]
    assert _by_depth()[Depth.ENGAGED].focus_team == demo_home.team_id


def test_the_focus_validator_is_what_rejects_a_team_lens_with_no_side():
    rows = json.loads(lenses.LENSES_PATH.read_text())["lenses"]
    team_row = next(r for r in rows if r["scope"] == "team")
    match_row = next(r for r in rows if r["scope"] == "match")
    with pytest.raises(ValidationError, match="focus_team"):
        Lens.model_validate({**team_row, "focus_team": None})
    with pytest.raises(ValidationError, match="focus_team"):
        Lens.model_validate({**match_row, "focus_team": team_row["focus_team"]})


def test_focus_player_is_null_on_every_lens():
    assert [lens.focus_player for lens in lenses.all_lenses()] == [None, None, None]


def test_breakthrough_types_are_goals_only():
    for lens in lenses.all_lenses():
        assert lens.breakthrough_types == (MomentType.GOAL,)


def test_every_depth_hears_comparisons():
    """Casual used to drop them. It hears them now, because the score is a comparison and the
    casual viewer is told what a goal did to it, in words (26 Oct); what casual says of a
    comparison still carries no number."""
    for lens in _by_depth().values():
        assert ClaimType.COMPARATIVE in lens.allowed_claim_types


# --- invariant 10 --------------------------------------------------------------------------------


def test_no_lens_id_is_a_string_literal_in_code_outside_config():
    ids = _lens_ids()
    offenders = []
    for path in (REPO_ROOT / "matchlens").rglob("*.py"):
        relative = path.relative_to(REPO_ROOT)
        if "config" in relative.parts[:2]:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and node.value in ids:
                offenders.append(f"{relative}:{node.lineno}")
    assert offenders == []


def test_a_fourth_lens_is_a_row_and_no_code_changes(monkeypatch):
    four = lenses.load(FOUR_LENSES)
    assert len(four) == 4
    monkeypatch.setattr(lenses, "_LENSES", tuple(four))
    assert [lens.lens_id for lens in lenses.all_lenses()] == [
        "fx_casual",
        "fx_analyst",
        "fx_engaged",
        "fx_fourth",
    ]
    assert lenses.get("fx_fourth").focus_team == "m-1-away"


# --- calibration ---------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def demo_importances() -> list[float]:
    ingest = Ingest()
    understanding = Understanding(ingest.record)
    spotter = Spotter(ingest.record, understanding.epoch_at)
    found = []
    for item in simulate(settings.match_seed):
        ingest.accept(item)
        if isinstance(item, MatchSetup):
            continue
        found += [r.moment.importance for r in spotter.consider(understanding.observe(item), item)]
    return found


def _admitted(importances: list[float], lens: Lens) -> int:
    return sum(i >= lens.importance_threshold for i in importances)


def test_the_thresholds_separate_on_the_demo_match(demo_importances):
    by_depth = _by_depth()
    casual = _admitted(demo_importances, by_depth[Depth.CASUAL])
    engaged = _admitted(demo_importances, by_depth[Depth.ENGAGED])
    analyst = _admitted(demo_importances, by_depth[Depth.ANALYST])
    assert 0 < casual < engaged < analyst
