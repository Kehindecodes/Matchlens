"""Parameter sets that shape the shape of a generated match.

An archetype says how the match is *driven*: who has the upper hand over the clock, how hard each
side presses, and the scripted football events (goals, substitutions, a sending-off). It never
says what is *interesting*. Selection happens later, from the record (D8, D12).

Minutes are elapsed match-clock minutes. Piecewise-linear schedules interpolate between points.
"""

from dataclasses import dataclass
from typing import Literal

Side = Literal["home", "away"]
Schedule = tuple[tuple[float, float], ...]  # (minute, value)


@dataclass(frozen=True)
class GoalPlan:
    """A goal the generator steers the match towards. Goals are never left to chance, so the
    shape of the scoreline is the archetype's, while their timing and build-up vary by seed."""

    minute: float  # not before; jittered by the seed
    side: Side


@dataclass(frozen=True)
class SubPlan:
    """Substitutions taken together at the first stoppage on or after `minute`."""

    side: Side
    minute: float
    roles: tuple[str, ...]  # the outgoing player's role, one entry per swap


@dataclass(frozen=True)
class RedCardPlan:
    """The first foul by `side` on or after `minute` is a sending-off."""

    side: Side
    minute: float


@dataclass(frozen=True)
class ArchetypeParams:
    archetype_id: str
    momentum: Schedule  # +1 the home side is on top, -1 the away side is
    home_press: Schedule  # 0 sits off, 1 presses hard when out of possession
    away_press: Schedule
    goals: tuple[GoalPlan, ...]
    subs: tuple[SubPlan, ...] = ()
    red_cards: tuple[RedCardPlan, ...] = ()
    # How well each side keeps the ball, -1 to 1: it offsets the other side's press on that
    # side's passes and carries. 0, the default, leaves the match exactly as without it.
    home_retention: Schedule = ((0, 0.0),)
    away_retention: Schedule = ((0, 0.0),)


# The demo narrative. Away score first on a counter while home are on top; home level while
# being pinned back (an equaliser against the run of play); home change two players at 58:00,
# press harder, and with the away side down to ten win it late.
COMEBACK = ArchetypeParams(
    archetype_id="comeback",
    momentum=(
        (0, 0.35),
        (15, 0.5),
        (22, 0.1),
        (28, -0.5),
        (44, -0.55),
        (47, -0.15),
        (56, 0.0),
        (62, 0.6),
        (75, 0.7),
        (100, 0.6),
    ),  # fmt: skip
    home_press=((0, 0.45), (45, 0.4), (57, 0.4), (60, 0.85), (100, 0.85)),
    away_press=((0, 0.4), (20, 0.55), (45, 0.5), (63, 0.3), (100, 0.25)),
    goals=(GoalPlan(18, "away"), GoalPlan(34, "home"), GoalPlan(76, "home")),
    subs=(
        SubPlan("home", 58.0, ("MF", "FW")),
        SubPlan("away", 71.0, ("DF",)),
        SubPlan("home", 80.0, ("MF",)),
    ),
    red_cards=(RedCardPlan("away", 63.0),),
)

# Home on top from first to last. Away sit deep with little of the ball but counter-press hard
# the moment they lose it, so their press stays high while their possession stays low.
ONE_SIDED = ArchetypeParams(
    archetype_id="one_sided",
    momentum=((0, 0.6), (20, 0.75), (45, 0.7), (50, 0.6), (70, 0.8), (100, 0.75)),
    home_press=((0, 0.5), (100, 0.45)),
    away_press=((0, 0.8), (60, 0.85), (100, 0.75)),
    goals=(GoalPlan(24, "home"), GoalPlan(58, "home"), GoalPlan(81, "home")),
    home_retention=((0, 0.8), (100, 0.8)),  # home keep the ball under the press (Q16)
    subs=(
        SubPlan("away", 55.0, ("MF",)),
        SubPlan("home", 66.0, ("FW", "MF")),
        SubPlan("away", 72.0, ("FW",)),
    ),
)

# Neither side gets on top for long: momentum drifts gently either side of level, both press
# moderately, and the one goal comes late.
TIGHT = ArchetypeParams(
    archetype_id="tight",
    momentum=(
        (0, 0.05),
        (15, -0.12),
        (30, 0.1),
        (45, -0.08),
        (60, 0.12),
        (75, -0.1),
        (88, 0.08),
        (100, 0.0),
    ),  # fmt: skip
    home_press=((0, 0.45), (100, 0.5)),
    away_press=((0, 0.5), (100, 0.45)),
    goals=(GoalPlan(84, "away"),),
    subs=(SubPlan("home", 65.0, ("MF",)), SubPlan("away", 70.0, ("FW",))),
)

# Both sides press high and the upper hand changes every few minutes, so the ball keeps changing
# hands: short possessions, many challenges, many fouls and restarts.
SCRAPPY = ArchetypeParams(
    archetype_id="scrappy",
    momentum=(
        (0, 0.3),
        (5, -0.35),
        (11, 0.4),
        (16, -0.3),
        (22, 0.35),
        (28, -0.4),
        (34, 0.3),
        (40, -0.35),
        (46, 0.3),
        (52, -0.4),
        (58, 0.35),
        (64, -0.3),
        (70, 0.4),
        (76, -0.35),
        (82, 0.3),
        (88, -0.3),
        (100, 0.2),
    ),  # fmt: skip
    home_press=((0, 0.85), (100, 0.8)),
    away_press=((0, 0.85), (100, 0.85)),
    goals=(GoalPlan(31, "home"), GoalPlan(69, "away")),
    subs=(SubPlan("home", 60.0, ("MF", "DF")), SubPlan("away", 62.0, ("MF",))),
    red_cards=(RedCardPlan("home", 74.0),),
)

ARCHETYPES = {a.archetype_id: a for a in (COMEBACK, ONE_SIDED, TIGHT, SCRAPPY)}


def interpolate(schedule: Schedule, minute: float) -> float:
    if minute <= schedule[0][0]:
        return schedule[0][1]
    for (m0, v0), (m1, v1) in zip(schedule, schedule[1:], strict=False):
        if minute <= m1:
            return v0 + (v1 - v0) * (minute - m0) / (m1 - m0)
    return schedule[-1][1]
