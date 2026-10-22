"""The four v1 signals, measured for one team over one window (U3, D24).

Each signal function takes a `SignalWindow` and a team id and returns a `Sample`: the value in
the signal's own units and `n`, how many things it was measured from. `measure` wraps that with
the clamped window and a confidence. Baselines and z-scores are U4's; nothing here judges what is
interesting. `line_height` is deferred (D24), so nothing here reads a frame.

All four are event-derived, and on-ball events only happen while play is live, so stopped time
adds nothing to any of them.
"""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

from matchlens import calltrace
from matchlens.config import settings
from matchlens.ingest import RecordReader
from matchlens.models import Action, Epoch, Event, Match, Possession, Signal, Zone
from matchlens.understanding.possession import sequence, zone
from matchlens.understanding.shot_value import is_shot, value


@dataclass(frozen=True)
class Interval:
    """`(start_ms, end_ms]`: the start is left out and the end is counted.

    A reading at clock X counts what happened at X. A window starting at an epoch's start leaves
    out the event that opened the epoch (the goal, the red card), which belongs to the epoch
    before. Frames use the same convention (`FrameAccess.frame_window`), so line height can join
    later without a second one.
    """

    start_ms: int
    end_ms: int

    @property
    def width_ms(self) -> int:
        return self.end_ms - self.start_ms

    def events(self, reader: RecordReader) -> tuple[Event, ...]:
        # events_between is [from, to); shifting both ends by 1 ms makes it (start, end].
        return reader.events_between(self.start_ms + 1, self.end_ms + 1)

    def possessions(self, reader: RecordReader) -> list[Possession]:
        return sequence(reader, self.start_ms + 1, self.end_ms + 1)


def window_at(clock_ms: int, epoch: Epoch, nominal_ms: int = settings.signal_window_ms) -> Interval:
    """The signal window for a reading at `clock_ms`, clamped to the epoch's start (D15)."""
    return Interval(max(clock_ms - nominal_ms, epoch.start_clock_ms), clock_ms)


@dataclass(frozen=True)
class SignalWindow:
    """What one window holds, read once and shared by every signal and both teams."""

    match: Match
    interval: Interval
    events: tuple[Event, ...]
    possessions: tuple[Possession, ...]

    @classmethod
    def read(cls, reader: RecordReader, interval: Interval) -> "SignalWindow":
        return cls(
            reader.match, interval, interval.events(reader), tuple(interval.possessions(reader))
        )


@dataclass(frozen=True)
class Sample:
    value: float
    n: int


def territory(window: SignalWindow, team: str) -> Sample:
    """Share of the possessions that reached a final third that were `team`'s. 0–1, 0.5 even.

    `n` is the number of possessions, by either team, that ended in their final third.
    """
    reached = [p for p in window.possessions if p.end_zone is Zone.FINAL_THIRD]
    ours = sum(p.team == team for p in reached)
    return Sample(ours / len(reached) if reached else 0.5, len(reached))


def possession_control(window: SignalWindow, team: str) -> Sample:
    """Share of the window's passes made by `team` inside its own possessions. 0–1, 0.5 even.

    Measured in passes strung together, not in time (DATA-MODEL: possession control is about
    sequences). `n` is the number of possessions in the window.
    """
    passes = sum(p.pass_count for p in window.possessions)
    ours = sum(p.pass_count for p in window.possessions if p.team == team)
    return Sample(ours / passes if passes else 0.5, len(window.possessions))


_DEFENSIVE_ACTIONS = frozenset({Action.TACKLE, Action.INTERCEPTION, Action.FOUL})


def pressing_intensity(window: SignalWindow, team: str) -> Sample:
    """Opponent passes allowed per defensive action by `team` (PPDA). Lower is a harder press.

    Counts the opponent's passes from its own defensive and middle thirds, and `team`'s tackles,
    interceptions and fouls in those same two thirds. With no defensive action the value is the
    pass count, as though there had been one. `n` is passes plus actions.
    """
    passes = actions = 0
    for e in window.events:
        if e.team is None or e.start_x is None:
            continue
        if e.team != team and e.action is Action.PASS:
            passes += zone(window.match, e) is not Zone.FINAL_THIRD
        elif e.team == team and e.action in _DEFENSIVE_ACTIONS:
            actions += zone(window.match, e) is not Zone.DEFENSIVE_THIRD
    return Sample(passes / max(actions, 1), passes + actions)


def chance_quality(window: SignalWindow, team: str) -> Sample:
    """Summed shot quality of `team`'s shots in the window. 0 upwards. Never called xG.

    `n` is the number of shots.
    """
    shots = [value(e, window.match) for e in window.events if e.team == team and is_shot(e)]
    return Sample(sum(s.value for s in shots), len(shots))


SIGNALS: dict[Signal, Callable[[SignalWindow, str], Sample]] = {
    Signal.TERRITORY: territory,
    Signal.POSSESSION_CONTROL: possession_control,
    Signal.PRESSING_INTENSITY: pressing_intensity,
    Signal.CHANCE_QUALITY: chance_quality,
    # Signal.LINE_HEIGHT is deferred (D24): it stays in the enum and has no function in v1.
}


@dataclass(frozen=True)
class Measurement:
    """One signal for one team at one clock: what U4 turns into a `SignalReading`."""

    signal: Signal
    team: str
    clock_ms: int
    epoch_id: str
    window_ms: int  # the clamped width, which is what the reading's `window_ms` holds
    value: float
    n: int
    confidence: float


# A window with nothing in it gives most signals a stand-in value (an even share, no presses)
# that says nothing about the match. Chance quality's 0 is different: "no chances" is a reading.
EMPTY_IS_A_READING = frozenset({Signal.CHANCE_QUALITY})


def is_placeholder(measurement: Measurement) -> bool:
    """Whether this measurement saw nothing and its value is a stand-in, not a reading (D28)."""
    return measurement.n == 0 and measurement.signal not in EMPTY_IS_A_READING


def confidence(n: int, k: int = settings.signal_confidence_k) -> float:
    """0 with no samples, one half at `k`, approaching 1. Falls as the sample thins."""
    return n / (n + k)


def measure(reader: RecordReader, epoch: Epoch, clock_ms: int) -> list[Measurement]:
    """Every v1 signal for both teams at `clock_ms`, over the window clamped to `epoch`."""
    calltrace.entered("Understanding")
    interval = window_at(clock_ms, epoch)
    window = SignalWindow.read(reader, interval)
    return [
        Measurement(
            signal=signal,
            team=team.team_id,
            clock_ms=clock_ms,
            epoch_id=epoch.epoch_id,
            window_ms=interval.width_ms,
            value=sample.value,
            n=sample.n,
            confidence=confidence(sample.n),
        )
        for team in reader.match.teams
        for signal, fn in SIGNALS.items()
        for sample in [fn(window, team.team_id)]
    ]


def cadence(epochs: Sequence[Epoch], end_ms: int) -> Iterator[tuple[int, Epoch]]:
    """Each reading clock up to `end_ms`, every `signal_cadence_ms`, with the epoch it falls in."""
    step = settings.signal_cadence_ms
    for clock in range(step, end_ms + 1, step):
        epoch = next((e for e in reversed(epochs) if e.start_clock_ms < clock), None)
        if epoch is not None:
            yield clock, epoch
