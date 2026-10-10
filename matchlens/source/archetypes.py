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

ARCHETYPES = {COMEBACK.archetype_id: COMEBACK}


def interpolate(schedule: Schedule, minute: float) -> float:
    if minute <= schedule[0][0]:
        return schedule[0][1]
    for (m0, v0), (m1, v1) in zip(schedule, schedule[1:], strict=False):
        if minute <= m1:
            return v0 + (v1 - v0) * (minute - m0) / (m1 - m0)
    return schedule[-1][1]
