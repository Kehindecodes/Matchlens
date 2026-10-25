"""The match clock and score as a stream message.

`MatchState` is sent, never stored: like `MatchSetup` it is not one of the data model's entities,
and it can always be recomputed from the event log. It travels the same path as renditions, so
the per-session release (D1) delays the score exactly as it delays a card.

The score is a fold over the event log (invariant 2, D16): a goal is an event whose outcome is
`goal`, and it counts for that event's team, the same rule the epochs' `score_state` uses.
"""

from pydantic import BaseModel, ConfigDict

from matchlens.models import ClockMs, Event, Frame, Outcome, Team
from matchlens.source import MatchSetup


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
    """Turns the stream into a `MatchState` each time the match clock reaches a new second, and
    at once when a goal changes the score, so the scoreboard is never a second behind it."""

    def __init__(self, setup: MatchSetup):
        home, away = sorted(setup.match.teams, key=lambda team: not team.is_home)
        self._teams: tuple[Team, Team] = (home, away)
        self._goals = {team.team_id: 0 for team in self._teams}
        self._last_second = -1

    def observe(self, item: Frame | Event) -> MatchState | None:
        scored = isinstance(item, Event) and item.outcome is Outcome.GOAL and item.team is not None
        if scored:
            self._goals[item.team] += 1
        second = item.clock_ms // 1000
        if second <= self._last_second and not scored:
            return None
        self._last_second = max(self._last_second, second)
        home, away = (
            TeamScore(
                team_id=team.team_id, short_name=team.short_name, goals=self._goals[team.team_id]
            )
            for team in self._teams
        )
        return MatchState(
            seq=item.seq, clock_ms=item.clock_ms, period=item.period, score=(home, away)
        )
