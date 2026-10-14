"""The match clock and score as a stream message.

`MatchState` is sent, never stored: like `MatchSetup` it is not one of the data model's entities,
and it can always be recomputed from the event log. It travels the same path as renditions, so
the per-session release (D1) delays the score exactly as it delays a card.

The score is a fold over the event log, which is Kehinde's to write. `MatchStateTracker` takes it
as a callable; until it exists the app passes `no_score`, and every score reads 0.
"""

from collections.abc import Callable, Mapping

from pydantic import BaseModel, ConfigDict

from matchlens.models import ClockMs, Event, Frame, Team
from matchlens.source import MatchSetup

ScoreAt = Callable[[int], Mapping[str, int]]  # match clock -> goals per team_id


def no_score(clock_ms: int) -> Mapping[str, int]:
    """Placeholder until the score fold exists: no team has scored."""
    return {}


class TeamScore(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    team_id: str
    short_name: str
    goals: int


class MatchState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seq: int  # of the stream item that produced it, so it orders against the stream
    clock_ms: ClockMs
    period: int
    score: tuple[TeamScore, TeamScore]  # home first


class MatchStateTracker:
    """Turns the stream into a `MatchState` each time the match clock reaches a new second."""

    def __init__(self, setup: MatchSetup, score: ScoreAt = no_score):
        home, away = sorted(setup.match.teams, key=lambda t: not t.is_home)
        self._teams: tuple[Team, Team] = (home, away)
        self._score = score
        self._last_second = -1

    def observe(self, item: Frame | Event) -> MatchState | None:
        second = item.clock_ms // 1000
        if second <= self._last_second:
            return None
        self._last_second = second
        goals = self._score(item.clock_ms)
        home, away = (
            TeamScore(team_id=t.team_id, short_name=t.short_name, goals=goals.get(t.team_id, 0))
            for t in self._teams
        )
        return MatchState(
            seq=item.seq, clock_ms=item.clock_ms, period=item.period, score=(home, away)
        )
