"""Replay harness: play a generated match back against a controllable clock.

The stream already carries its own time (`clock_ms` on every frame and event), so replay is only
a question of *when* to release each item. A `Replay` keeps a position on the match clock and a
cursor into the stream. While playing, the position advances at `speed` match-seconds per wall
second; an item is released once the position reaches its `clock_ms`.

Because the cursor is just an index into an immutable list, the controls are cheap and safe:

- pause freezes the position, and resume carries on from the same cursor, so nothing is skipped
  or repeated;
- seek moves the position and re-finds the cursor, forwards or backwards. Seeking backwards
  re-yields items already sent (so `seq` goes backwards for the consumer, which must expect it).
"""

import argparse
import bisect
import time
from collections.abc import Callable, Iterable, Iterator, Sequence

from matchlens.config.settings import settings
from matchlens.models import Action, Event, Frame, Outcome
from matchlens.source.archetypes import DEMO, ArchetypeParams
from matchlens.source.simulator import simulate
from matchlens.source.stream import MatchSetup, StreamItem

FAST_SPEED = 25.0

_EPS_MS = 1e-3  # absorbs float rounding so an item due "now" is not missed by a hair
_MIN_NAP_S = 1e-6
_MAX_NAP_S = 0.1  # naps are capped so pause, seek and speed changes take effect promptly
_IDLE_S = 0.05  # how often a paused stream checks whether it has been resumed


class Replay:
    """A stream, a position on the match clock, and play / pause / seek / speed controls.

    Single consumer: the controls share one cursor. Drive it either by iterating it (`stream()`,
    which paces itself with `sleep`) or by calling `poll()` from your own loop.
    """

    def __init__(
        self,
        items: Iterable[StreamItem],
        *,
        speed: float = 1.0,
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        everything = list(items)
        if not everything or not isinstance(everything[0], MatchSetup):
            raise ValueError("the stream must start with the MatchSetup roster")
        body: list[Frame | Event] = []
        last_seq = -1
        for item in everything[1:]:
            if not isinstance(item, Frame | Event):
                raise ValueError(f"unexpected item in the stream: {type(item).__name__}")
            if item.seq <= last_seq:
                raise ValueError("the stream must be in strictly increasing seq order")
            last_seq = item.seq
            body.append(item)
        self.setup: MatchSetup = everything[0]
        self._items: Sequence[Frame | Event] = body
        self._clocks = [i.clock_ms for i in body]
        self._now = now
        self._sleep = sleep
        self._speed = self._checked_speed(speed)
        self._cursor = 0
        self._playing = False
        self._started = False
        self._anchor_wall = 0.0
        self._anchor_pos = 0.0  # ms; the position at the anchor, and while paused

    @classmethod
    def from_seed(
        cls,
        seed: int | None = None,
        archetype: ArchetypeParams = DEMO,
        *,
        frame_rate_hz: int | None = None,
        **kwargs,
    ) -> "Replay":
        return cls(simulate(seed, archetype, frame_rate_hz=frame_rate_hz), **kwargs)

    # --- state ------------------------------------------------------------------------------

    @staticmethod
    def _checked_speed(speed: float) -> float:
        if not speed > 0:
            raise ValueError("speed must be a positive multiplier")
        return float(speed)

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def finished(self) -> bool:
        return self._cursor >= len(self._items)

    @property
    def duration_ms(self) -> int:
        return self._clocks[-1] if self._clocks else 0

    @property
    def position_ms(self) -> float:
        """Where the replay is on the match clock."""
        if not self._playing:
            return self._anchor_pos
        return self._anchor_pos + self._speed * (self._now() - self._anchor_wall) * 1000.0

    # --- controls ---------------------------------------------------------------------------

    def play(self) -> None:
        if self._playing:
            return
        self._anchor_wall = self._now()
        self._playing = True
        self._started = True

    def pause(self) -> None:
        if not self._playing:
            return
        self._anchor_pos = self.position_ms
        self._playing = False

    def seek(self, clock_ms: float) -> None:
        """Jump to `clock_ms`. Items before it are skipped, and items from it onwards are sent."""
        if clock_ms < 0:
            raise ValueError("cannot seek before kickoff")
        self._anchor_pos = float(clock_ms)
        self._anchor_wall = self._now()
        self._cursor = bisect.bisect_left(self._clocks, clock_ms)

    def set_speed(self, speed: float) -> None:
        speed = self._checked_speed(speed)
        self._anchor_pos = self.position_ms  # rebase so the change applies from now on
        self._anchor_wall = self._now()
        self._speed = speed

    # --- releasing items --------------------------------------------------------------------

    def _take_due(self) -> Frame | Event | None:
        if not self._playing or self.finished:
            return None
        if self._clocks[self._cursor] > self.position_ms + _EPS_MS:
            return None
        item = self._items[self._cursor]
        self._cursor += 1
        return item

    def poll(self) -> list[Frame | Event]:
        """Every item that has become due since the last call, in `seq` order. The roster is not
        included; it is `self.setup`. Empty while paused."""
        out = []
        while (item := self._take_due()) is not None:
            out.append(item)
        return out

    def next_due_in(self) -> float | None:
        """Wall seconds until the next item is due, or None if paused or finished."""
        if not self._playing or self.finished:
            return None
        return max((self._clocks[self._cursor] - self.position_ms) / (self._speed * 1000.0), 0.0)

    def stream(self) -> Iterator[StreamItem]:
        """The roster, then every frame and event as it falls due. Starts playing if the replay
        was never started. While paused it idles until something resumes it."""
        yield self.setup
        if not self._started:
            self.play()
        while not self.finished:
            item = self._take_due()
            if item is not None:
                yield item  # the consumer may pause, seek or change speed here
                continue
            wait = self.next_due_in()
            self._sleep(_IDLE_S if wait is None else max(min(wait, _MAX_NAP_S), _MIN_NAP_S))

    __iter__ = stream


# --- command line ----------------------------------------------------------------------------

_KEY_ACTIONS = {
    Action.PERIOD_START,
    Action.PERIOD_END,
    Action.ADDED_TIME_ANNOUNCED,
    Action.SUBSTITUTION,
    Action.RED_CARD,
    Action.YELLOW_CARD,
}


def _mmss(ms: int) -> str:
    return f"{ms // 60_000:02d}:{ms // 1000 % 60:02d}"


def _describe(e: Event, names: dict[str, str], shorts: dict[str, str]) -> str:
    team = shorts.get(e.team or "", "")
    who = names.get(e.player or "", "")
    if e.action is Action.PERIOD_START:
        return f"Kick off, half {e.period}"
    if e.action is Action.PERIOD_END:
        return f"End of half {e.period}"
    if e.action is Action.ADDED_TIME_ANNOUNCED:
        return f"Added time announced: {(e.added_time_ms or 0) // 60_000} min"
    if e.action is Action.SUBSTITUTION:
        return f"{team}  sub: {who} off, {names.get(e.player_on or '', '?')} on"
    if e.action in (Action.RED_CARD, Action.YELLOW_CARD):
        return f"{team}  {who}  {e.action.value.replace('_', ' ')}"
    text = f"{team}  {who}  {e.action.value}"
    if e.receiver:
        text += f" to {names.get(e.receiver, e.receiver)}"
    return f"{text}  ({e.outcome.value})" if e.outcome else text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m matchlens.source.replay",
        description="Replay a generated match in the terminal.",
    )
    parser.add_argument("--seed", type=int, default=settings.match_seed)
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="match seconds per wall second; 25 plays a full match in under 4 minutes",
    )
    parser.add_argument("--hz", type=int, default=None, help="frame rate (default: settings)")
    parser.add_argument("--key-only", action="store_true", help="goals, cards, subs and halves")
    args = parser.parse_args(argv)

    replay = Replay.from_seed(args.seed, frame_rate_hz=args.hz, speed=args.speed)
    names = {p.player_id: p.name for p in replay.setup.players}
    shorts = {t.team_id: t.short_name for t in replay.setup.match.teams}
    home, away = sorted(replay.setup.match.teams, key=lambda t: not t.is_home)
    score = {home.team_id: 0, away.team_id: 0}
    print(f"{home.name} v {away.name}   seed {args.seed}   {args.speed:g}x")

    last = 0
    try:
        for item in replay:
            if not isinstance(item, Event):
                continue
            last = item.clock_ms
            if item.action is Action.VAR_OVERTURNED and item.team in score:
                score[item.team] -= 1
                print(f"{_mmss(item.clock_ms)}  VAR   goal ruled out ({item.var_reason})")
            elif item.outcome is Outcome.GOAL and item.team in score:
                score[item.team] += 1
                tally = (
                    f"{shorts[home.team_id]} {score[home.team_id]}-{score[away.team_id]} "
                    f"{shorts[away.team_id]}"
                )
                print(f"{_mmss(item.clock_ms)}  GOAL  {names[item.player or '']}  {tally}")
            elif not args.key_only or item.action in _KEY_ACTIONS:
                print(f"{_mmss(item.clock_ms)}  {_describe(item, names, shorts)}")
    except KeyboardInterrupt:
        print(f"\nStopped at {_mmss(last)}")
        return 130
    print(
        f"Full time  {shorts[home.team_id]} {score[home.team_id]}-{score[away.team_id]} "
        f"{shorts[away.team_id]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
