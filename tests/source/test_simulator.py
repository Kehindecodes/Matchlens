"""F3 acceptance criteria for the seeded simulator."""

import re
from pathlib import Path
from statistics import mean, pstdev

from matchlens.config.settings import settings
from matchlens.models import Action, Event, Frame, Outcome, Phase
from matchlens.source.archetypes import COMEBACK
from matchlens.source.simulator import PRESSING_DISTANCE_M, simulate
from matchlens.source.stream import MatchSetup
from tests.source.helpers import Played, attack_x, was_on_pitch

INTERVAL_MS = 1000 // settings.frame_rate_hz
MIN = 60_000
ON_BALL = [a for a in Action if a not in {
    Action.SUBSTITUTION, Action.RED_CARD, Action.YELLOW_CARD, Action.PERIOD_START,
    Action.PERIOD_END,
}]  # fmt: skip
REPO = Path(__file__).resolve().parents[2]


def goals(played: Played) -> list[Event]:
    return [e for e in played.events if e.outcome is Outcome.GOAL]


def on_ball_events(played: Played) -> list[Event]:
    return [e for e in played.events if e.action in ON_BALL]


# --- determinism (invariant 9) ---------------------------------------------------------------
# The byte-identical test (same seed twice, compared serialised) is deliberately absent: Kehinde
# writes it himself (docs/tickets/F3.md). These guard the conditions it depends on.


def test_simulator_uses_no_global_rng_and_no_wall_time():
    for path in (REPO / "matchlens" / "source").glob("*.py"):
        text = path.read_text()
        assert not re.search(r"^\s*(import random|from random)\b", text, re.M), path
        assert not re.search(r"np\.random\.(?!default_rng|Generator)", text), path
        assert not re.search(r"\b(time\.time|perf_counter|monotonic|datetime\.now|utcnow)\b", text)


def test_default_seed_is_the_demo_seed_in_settings():
    first = next(iter(simulate()))
    assert isinstance(first, MatchSetup)
    assert first.match.seed == settings.match_seed


def test_different_seeds_produce_visibly_different_matches(match_1, match_2):
    assert match_1.setup.match.teams[0].name != match_2.setup.match.teams[0].name or (
        match_1.setup.players[0].name != match_2.setup.players[0].name
    )
    a = {(e.action, e.clock_ms) for e in match_1.events}
    b = {(e.action, e.clock_ms) for e in match_2.events}
    assert len(a & b) / len(a) < 0.25
    assert [g.clock_ms for g in goals(match_1)] != [g.clock_ms for g in goals(match_2)]


# --- volume and timing -----------------------------------------------------------------------


def test_about_1800_events_per_match(match_1, match_2):
    for m in (match_1, match_2):
        assert 1650 <= len(m.events) <= 1950


def test_one_event_every_three_to_four_seconds_of_match_time(match_1):
    # The brief says "3-4 s of play" but also ~1,800 events and 55-65 in-play minutes, which cannot
    # all hold: 1,800 events over ~60 in-play minutes is one per ~2 s. It holds over elapsed match
    # time (~96 min / 1,800 = ~3.2 s), which is how it is read here. See docs/QUESTIONS.md Q2.
    gap_s = match_1.end_clock_ms / len(match_1.events) / 1000
    assert 2.8 <= gap_s <= 4.0


def test_frames_are_emitted_at_exactly_the_configured_rate(match_1):
    clocks = [f.clock_ms for f in match_1.frames]
    assert clocks[0] == 0
    assert {b - a for a, b in zip(clocks, clocks[1:], strict=False)} == {INTERVAL_MS}


def test_frame_rate_comes_from_settings_not_a_constant(monkeypatch):
    monkeypatch.setattr(settings, "frame_rate_hz", 1)
    frames = [i for i in simulate(1, COMEBACK) if isinstance(i, Frame)]
    assert {b.clock_ms - a.clock_ms for a, b in zip(frames, frames[1:], strict=False)} == {1000}


def test_seq_is_monotonic_across_frames_and_events(match_1):
    seqs = [i.seq for i in match_1.items[1:]]
    assert seqs == list(range(len(seqs)))


def test_clock_never_goes_backwards_in_the_stream(match_1):
    clocks = [i.clock_ms for i in match_1.items[1:]]
    assert clocks == sorted(clocks)


# --- phases ----------------------------------------------------------------------------------


def test_all_three_phases_appear_and_in_play_time_is_plausible(match_1):
    phases = {f.phase for f in match_1.frames}
    assert phases == {Phase.IN_PLAY, Phase.STOPPED, Phase.SET_PIECE}
    in_play_min = sum(f.phase is Phase.IN_PLAY for f in match_1.frames) * INTERVAL_MS / MIN
    assert 55 <= in_play_min <= 65


def test_no_open_play_action_happens_while_stopped(match_1):
    frame_phase = {f.seq: f.phase for f in match_1.frames}
    for e in match_1.events:
        if e.action in (Action.PASS, Action.CARRY, Action.SHOT, Action.TACKLE, Action.CLEARANCE):
            assert frame_phase[e.frame_ref] is not Phase.STOPPED, e


# --- event / frame alignment -----------------------------------------------------------------


def test_every_event_frame_ref_is_within_half_a_frame_interval(match_1):
    by_seq = {f.seq: f for f in match_1.frames}
    for e in match_1.events:
        assert abs(by_seq[e.frame_ref].clock_ms - e.clock_ms) <= INTERVAL_MS / 2, e


def test_event_ids_are_unique(match_1):
    ids = [e.event_id for e in match_1.events]
    assert len(ids) == len(set(ids))


def test_under_pressure_is_derived_from_positions_at_execution(match_1):
    by_seq = {f.seq: f for f in match_1.frames}
    teams = {p.player_id: p.team_id for p in match_1.setup.players}
    checked = agreed = 0
    for e in match_1.events:
        if e.action not in (Action.PASS, Action.CARRY) or e.under_pressure is None:
            continue
        frame = by_seq[e.frame_ref]
        actor = next((p for p in frame.players if p.player_id == e.player), None)
        if actor is None or abs(actor.x - e.start_x) > 0.5 or abs(actor.y - e.start_y) > 0.5:
            continue
        nearest = min(
            ((p.x - actor.x) ** 2 + (p.y - actor.y) ** 2) ** 0.5
            for p in frame.players
            if teams[p.player_id] != e.team
        )
        checked += 1
        agreed += (nearest < PRESSING_DISTANCE_M) == e.under_pressure
    assert checked > 500
    assert agreed / checked > 0.95


# --- roster before stream, match events, derived roster (D16) --------------------------------


def test_roster_is_the_first_item_and_precedes_every_frame_and_event(match_1):
    assert isinstance(match_1.items[0], MatchSetup)
    assert not any(isinstance(i, MatchSetup) for i in match_1.items[1:])
    setup = match_1.setup
    assert len(setup.match.teams) == 2
    assert len(setup.players) == 36
    ids = [p.player_id for p in setup.players]
    assert len(set(ids)) == 36
    assert len({p.name for p in setup.players}) == 36
    assert sum(p.is_starter for p in setup.players) == 22
    team_ids = {t.team_id for t in setup.match.teams}
    assert {p.team_id for p in setup.players} == team_ids


def test_every_event_references_known_players_and_teams(match_1):
    players = {p.player_id: p for p in match_1.setup.players}
    for e in match_1.events:
        for pid in (e.player, e.receiver, e.player_on):
            assert pid is None or pid in players, e
        if e.player is not None:
            assert players[e.player].team_id == e.team, e


def test_period_events_bracket_both_halves(match_1):
    starts = [e for e in match_1.events if e.action is Action.PERIOD_START]
    ends = [e for e in match_1.events if e.action is Action.PERIOD_END]
    assert [e.period for e in starts] == [1, 2]
    assert [e.period for e in ends] == [1, 2]
    assert 0 < starts[0].clock_ms < INTERVAL_MS // 2
    assert starts[0].clock_ms < ends[0].clock_ms <= starts[1].clock_ms < ends[1].clock_ms
    assert 45 * MIN < ends[0].clock_ms < 49 * MIN


def test_archetype_has_a_double_substitution_at_a_single_clock(match_1):
    subs = [e for e in match_1.events if e.action is Action.SUBSTITUTION]
    by_clock: dict[int, list[Event]] = {}
    for e in subs:
        by_clock.setdefault(e.clock_ms, []).append(e)
    double = [v for v in by_clock.values() if len(v) >= 2]
    assert double, "expected two substitutions at one clock"
    pair = double[0]
    assert pair[0].team == pair[1].team
    assert all(e.player_on is not None for e in pair)
    assert 58 * MIN <= pair[0].clock_ms <= 60 * MIN


def test_archetype_has_a_sending_off(match_1):
    reds = [e for e in match_1.events if e.action is Action.RED_CARD]
    assert len(reds) == 1
    assert reds[0].clock_ms >= 63 * MIN


def test_derived_roster_agrees_with_every_sampled_frame(match_1):
    players = match_1.setup.players
    for f in match_1.frames[::7]:
        expected = {
            p.player_id for p in players if was_on_pitch(match_1.windows, p.player_id, f.clock_ms)
        }
        assert {p.player_id for p in f.players} == expected, f.clock_ms


def test_frame_player_count_drops_after_the_sending_off_and_is_never_hardcoded(match_1):
    red = next(e for e in match_1.events if e.action is Action.RED_CARD)
    before = {len(f.players) for f in match_1.frames if f.clock_ms < red.clock_ms}
    after = {len(f.players) for f in match_1.frames if f.clock_ms > red.clock_ms}
    assert before == {22}
    assert after == {21}


def test_nobody_acts_after_leaving_the_pitch(match_1):
    for e in on_ball_events(match_1):
        assert was_on_pitch(match_1.windows, e.player, e.clock_ms), e


# --- coverage of actions ---------------------------------------------------------------------


def test_the_log_records_every_kind_of_action_not_only_the_interesting_ones(match_1):
    seen = {e.action for e in match_1.events}
    required = {
        Action.PASS, Action.CARRY, Action.SHOT, Action.TACKLE, Action.INTERCEPTION,
        Action.CLEARANCE, Action.FOUL, Action.THROW_IN, Action.CORNER, Action.GOAL_KICK,
        Action.FREE_KICK, Action.SAVE, Action.BLOCK, Action.AERIAL_DUEL, Action.YELLOW_CARD,
    }  # fmt: skip
    assert required <= seen, required - seen
    passes = sum(e.action is Action.PASS for e in match_1.events)
    shots = sum(e.action is Action.SHOT for e in match_1.events)
    assert passes > 20 * shots  # the boring denominator exists


# --- plausibility: the five signals must not be satisfiable by a coin flip -------------------


def test_possession_sequences_are_long_not_alternating(match_1):
    runs: list[int] = []
    switches = 0
    last_team = None
    for e in on_ball_events(match_1):
        if e.team == last_team:
            runs[-1] += 1
        else:
            runs.append(1)
            switches += last_team is not None
            last_team = e.team
    assert mean(runs) > 2
    assert switches / len(on_ball_events(match_1)) < 0.4


def test_territory_shifts_over_multi_minute_spells(match_1):
    home = match_1.setup.match.teams[0] if match_1.setup.match.teams[0].is_home else None
    home = home or match_1.setup.match.teams[1]

    def home_ball_x(lo: int, hi: int) -> float:
        xs = [
            attack_x(match_1, home.team_id, f.period, f.ball_x)
            for f in match_1.frames
            if lo * MIN <= f.clock_ms < hi * MIN and f.phase is Phase.IN_PLAY
        ]
        return mean(xs)

    early, middle, late = home_ball_x(2, 15), home_ball_x(26, 44), home_ball_x(66, 90)
    assert early > middle + 6
    assert late > middle + 6


def test_defensive_line_has_a_coherent_height_that_moves(match_1):
    home_id = next(t.team_id for t in match_1.setup.match.teams if t.is_home)
    defenders = {
        p.player_id for p in match_1.setup.players if p.team_id == home_id and p.position == "DF"
    }
    minute_heights: dict[int, list[float]] = {}
    for f in match_1.frames:
        if f.phase is not Phase.IN_PLAY:
            continue
        xs = [
            attack_x(match_1, home_id, f.period, p.x) + 52.5
            for p in f.players
            if p.player_id in defenders
        ]
        if len(xs) >= 3:
            minute_heights.setdefault(f.clock_ms // MIN, []).append(mean(xs))
    series = [mean(v) for _, v in sorted(minute_heights.items())]
    assert max(series) - min(series) > 6  # it moves
    steps = [abs(b - a) for a, b in zip(series, series[1:], strict=False)]
    assert mean(steps) < 3  # but not a coin flip from minute to minute


def test_pressing_intensity_can_change(match_1):
    home_id = next(t.team_id for t in match_1.setup.match.teams if t.is_home)

    def away_pressure_rate(lo: int, hi: int) -> float:
        evs = [
            e
            for e in match_1.events
            if e.action in (Action.PASS, Action.CARRY)
            and e.team != home_id
            and lo * MIN <= e.clock_ms < hi * MIN
        ]
        return mean(bool(e.under_pressure) for e in evs)

    assert away_pressure_rate(62, 90) > away_pressure_rate(2, 25) + 0.08


def test_shots_cluster_where_chances_come_from(match_1):
    shots = [e for e in match_1.events if e.action is Action.SHOT]
    assert len(shots) >= 15
    attacking = [attack_x(match_1, e.team, e.period, e.start_x) for e in shots]
    assert min(attacking) > 17.5  # final third only
    assert mean(x > 36 for x in attacking) > 0.4  # mostly in or around the box
    assert pstdev([e.start_y for e in shots]) < 14  # uniform over the width would be ~19.6


# --- the demo narrative ----------------------------------------------------------------------


def test_the_archetype_scripts_a_comeback_with_an_equaliser_against_the_run_of_play(match_1):
    home = next(t for t in match_1.setup.match.teams if t.is_home)
    scored = goals(match_1)
    assert len(scored) == 3
    score = {t.team_id: 0 for t in match_1.setup.match.teams}
    equaliser = None
    for g in scored:
        before = dict(score)
        score[g.team] += 1
        if before[g.team] + 1 == before[next(k for k in score if k != g.team)]:
            equaliser = g
    assert equaliser is not None
    assert equaliser.team == home.team_id
    assert score[home.team_id] == 2 and sum(score.values()) == 3

    # "Against the run of play": in the minutes before the goal, the ball was mostly in the
    # scoring team's own half.
    lo, hi = equaliser.clock_ms - 8 * MIN, equaliser.clock_ms - 45_000
    xs = [
        attack_x(match_1, equaliser.team, f.period, f.ball_x)
        for f in match_1.frames
        if lo <= f.clock_ms < hi and f.phase is Phase.IN_PLAY
    ]
    assert mean(xs) < -3
