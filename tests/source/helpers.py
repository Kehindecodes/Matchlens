"""Test-side helpers for reading a generated match.

`was_on_pitch` here is a reference implementation of the D16 formula, written independently of the
simulator so the two can disagree. The production version belongs with the log reader (A1).
"""

from dataclasses import dataclass
from functools import cached_property

from matchlens.models import Action, Event, Frame, Player
from matchlens.source.stream import MatchSetup, StreamItem


@dataclass(frozen=True)
class Played:
    setup: MatchSetup
    frames: list[Frame]
    events: list[Event]
    items: list[StreamItem]

    @property
    def end_clock_ms(self) -> int:
        return max(e.clock_ms for e in self.events if e.action is Action.PERIOD_END)

    def player(self, player_id: str) -> Player:
        return next(p for p in self.setup.players if p.player_id == player_id)

    @cached_property
    def windows(self) -> dict[str, tuple[int, int]]:
        return pitch_windows(self.setup.players, self.events, self.end_clock_ms)

    def team(self, team_id: str):
        return next(t for t in self.setup.match.teams if t.team_id == team_id)


def split(items: list[StreamItem]) -> Played:
    setup = items[0]
    assert isinstance(setup, MatchSetup)
    frames = [i for i in items if isinstance(i, Frame)]
    events = [i for i in items if isinstance(i, Event)]
    return Played(setup, frames, events, items)


def pitch_windows(
    players: tuple[Player, ...], events: list[Event], end_clock_ms: int
) -> dict[str, tuple[int, int]]:
    """D16: each player's [enters, leaves) window, derived from the log alone.

    A player enters at kickoff (starter) or on the substitution that brings them on, and leaves on
    the substitution taking them off, their red card, or the end. Inclusive start, exclusive end.
    A player who never enters gets an empty window.
    """
    enters = {p.player_id: 0 if p.is_starter else None for p in players}
    leaves = {p.player_id: end_clock_ms for p in players}
    for e in events:
        if e.action is Action.SUBSTITUTION:
            if e.player_on is not None and enters[e.player_on] is None:
                enters[e.player_on] = e.clock_ms
            leaves[e.player] = min(leaves[e.player], e.clock_ms)
        elif e.action is Action.RED_CARD:
            leaves[e.player] = min(leaves[e.player], e.clock_ms)
    return {
        pid: (end_clock_ms, end_clock_ms) if enters[pid] is None else (enters[pid], leaves[pid])
        for pid in enters
    }


def was_on_pitch(windows: dict[str, tuple[int, int]], player_id: str, clock_ms: int) -> bool:
    enters, leaves = windows[player_id]
    return enters <= clock_ms < leaves


def attack_x(played: Played, team_id: str, period: int, x: float) -> float:
    """`x` expressed so `team_id` attacks towards +x."""
    return x * played.team(team_id).attack_direction(period)
