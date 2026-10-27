"""Position readings: what the frames before a shot showed about how it came about (Q48).

Understanding is the only reader of frames (invariant 1). When a shot arrives, `Movement`
measures three things the event log cannot show and stores each as a `PositionReading`, which a
claim cites and the verifier checks against. Nothing here judges whether one is worth saying: a
reading is kept when the frames show it, and the claim builder speaks it or not.

- **overload**: in the last frame before the final pass (the shot's assist), the outfield
  players of each side within `movement_reach_m` of the ball. Kept only when the attackers
  outnumber the defenders.
- **decoy run**: over the `movement_decoy_ms` before the shot, a team-mate of the shooter who
  got `movement_decoy_min_m` farther from where the shot was struck, and an outfield defender
  who started within `movement_marker_start_m` of him, finished within `movement_marker_end_m`,
  and moved as far, the same way (`movement_follow_cos`). The defender drawn farthest is kept.
- **early run**: the shooter's ground covered over the `movement_early_ms` up to the last frame
  before the final pass, kept from `movement_early_min_m`.

The frames say where everyone was, never why. A decoy run is a team-mate who went away from the
shot with a defender beside him all the way; the words built on it say so and no more.
"""

import math
from collections.abc import Callable, Mapping, Sequence

from matchlens import calltrace
from matchlens.config import settings
from matchlens.ingest import FrameAccess, RecordReader
from matchlens.models import Event, Frame, Mechanism, Player, PositionReading
from matchlens.source import StreamItem
from matchlens.understanding.buildup import assist_of
from matchlens.understanding.shot_value import is_shot

_LOOKBACK_MS = 60_000  # events read back from a shot to find its assist; one pass is enough


class Movement:
    """Takes the position readings for each shot as it arrives. Holds no state of its own."""

    def __init__(self, frames: Callable[[], FrameAccess], record: Callable[[], RecordReader]):
        self._frames = frames
        self._record = record

    def observe(self, item: StreamItem) -> list[PositionReading]:
        """The readings `item` completes: some for a shot, none for anything else."""
        if not isinstance(item, Event) or not is_shot(item):
            return []
        calltrace.entered("Understanding")
        reader = self._record()
        events = reader.events_between(item.clock_ms - _LOOKBACK_MS, item.clock_ms + 1)
        return measure(item, events, self._frames(), reader.players)


def measure(
    shot: Event, events: Sequence[Event], frames: FrameAccess, players: Sequence[Player]
) -> list[PositionReading]:
    """The overload, decoy run and early run the frames show for `shot`, those it had."""
    roster = {p.player_id: p for p in players}
    readings = []
    assist = assist_of(events, shot)
    if assist is not None:
        before = frames.frame_window(assist.clock_ms, settings.movement_early_ms)
        if before:
            readings += _overload(shot, before[-1], roster)
            readings += _early_run(shot, before[0], before[-1])
    run = frames.frame_window(shot.clock_ms, settings.movement_decoy_ms)
    if len(run) >= 2:
        readings += _decoy_run(shot, run[0], run[-1], roster)
    return readings


def _reading(
    shot: Event,
    mechanism: Mechanism,
    frames: Sequence[Frame],
    value: float,
    *,
    player: str | None = None,
    opponent: str | None = None,
    against: float | None = None,
) -> PositionReading:
    assert shot.team is not None  # a shot always has a team
    return PositionReading(
        reading_id=f"{shot.event_id}-{mechanism.value}",
        mechanism=mechanism,
        team=shot.team,
        shot_id=shot.event_id,
        clock_ms=shot.clock_ms,
        start_ms=frames[0].clock_ms,
        end_ms=frames[-1].clock_ms,
        player=player,
        opponent=opponent,
        value=value,
        against=against,
        frame_seqs=tuple(dict.fromkeys(f.seq for f in frames)),
    )


def _outfield(roster: Mapping[str, Player], player_id: str) -> bool:
    player = roster.get(player_id)
    return player is not None and player.position != "GK"


def _overload(shot: Event, frame: Frame, roster: Mapping[str, Player]) -> list[PositionReading]:
    near = [
        roster[p.player_id].team_id
        for p in frame.players
        if _outfield(roster, p.player_id)
        and math.hypot(p.x - frame.ball_x, p.y - frame.ball_y) <= settings.movement_reach_m
    ]
    attackers = sum(team == shot.team for team in near)
    defenders = len(near) - attackers
    if attackers <= defenders:
        return []
    return [_reading(shot, Mechanism.OVERLOAD, [frame], float(attackers), against=float(defenders))]


def _early_run(shot: Event, first: Frame, last: Frame) -> list[PositionReading]:
    start, end = _where(first).get(shot.player or ""), _where(last).get(shot.player or "")
    if start is None or end is None or first.seq == last.seq:
        return []
    covered = round(math.dist(start, end), 1)
    if covered < settings.movement_early_min_m:
        return []
    return [_reading(shot, Mechanism.EARLY_RUN, [first, last], covered, player=shot.player)]


def _decoy_run(
    shot: Event, first: Frame, last: Frame, roster: Mapping[str, Player]
) -> list[PositionReading]:
    assert shot.start_x is not None and shot.start_y is not None  # a shot has a start
    struck = (shot.start_x, shot.start_y)
    start, end = _where(first), _where(last)
    both = [pid for pid in start if pid in end and _outfield(roster, pid)]
    mates = [pid for pid in both if roster[pid].team_id == shot.team and pid != shot.player]
    backs = [pid for pid in both if roster[pid].team_id != shot.team]
    best: tuple[float, str, str] | None = None
    for mate in mates:
        if math.dist(end[mate], struck) - math.dist(start[mate], struck) < (
            settings.movement_decoy_min_m
        ):
            continue
        ran = _step(start[mate], end[mate])
        for back in backs:
            if math.dist(start[mate], start[back]) > settings.movement_marker_start_m:
                continue
            if math.dist(end[mate], end[back]) > settings.movement_marker_end_m:
                continue
            went = _step(start[back], end[back])
            drawn = math.hypot(*went)
            if drawn < settings.movement_decoy_min_m:
                continue
            if _cos(ran, went) < settings.movement_follow_cos:
                continue
            if best is None or drawn > best[0]:
                best = (drawn, mate, back)
    if best is None:
        return []
    drawn, mate, back = best
    return [
        _reading(
            shot, Mechanism.DECOY_RUN, [first, last], round(drawn, 1), player=mate, opponent=back
        )
    ]


def _where(frame: Frame) -> dict[str, tuple[float, float]]:
    return {p.player_id: (p.x, p.y) for p in frame.players}


def _step(start: tuple[float, float], end: tuple[float, float]) -> tuple[float, float]:
    return end[0] - start[0], end[1] - start[1]


def _cos(first: tuple[float, float], second: tuple[float, float]) -> float:
    lengths = math.hypot(*first) * math.hypot(*second)
    if lengths == 0:
        return 0.0
    return (first[0] * second[0] + first[1] * second[1]) / lengths
