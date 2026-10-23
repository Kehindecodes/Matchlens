"""What the spotter has already said, so it does not say it again (M2).

M1 judges whether a reading is notable. This judges whether the moment would repeat one already
fired, which makes it the first thing here that remembers MatchLens's own output rather than the
match. Two rules, per `(signal, team)`:

- **Duplicate detection.** A shift is a state: over the threshold in one direction. While the
  series stays on that side of the release level (`spotter_z_release`) it is the same shift, so
  dipping under the threshold and coming back is not a new one. It ends when the series falls
  back to the release level, flips direction, or a reading too thin to trust arrives (a break
  has just reset the baseline, so the old state means nothing).
- **Cooldown.** Once a shift fires, that `(signal, team, type)` is silent for
  `spotter_cooldown_ms`, whichever direction the next one goes. A shift that begins inside the
  cooldown is blocked and is not queued: it is not reported when the cooldown ends.

Goals never come here: they are events, and a goal is a goal however recently anything fired.
One `Suppression` per match, so two matches in one process cannot suppress each other.
"""

from matchlens.config import settings
from matchlens.models import MomentType, Signal, SignalReading


class Suppression:
    def __init__(self) -> None:
        self._direction: dict[tuple[Signal, str], int] = {}
        self._fired_at_ms: dict[tuple[Signal, str, MomentType], int] = {}

    def admits_shift(self, reading: SignalReading, trusted: bool) -> bool:
        """Whether this reading is a new shift that is not inside a cooldown.

        `trusted` is whether the reading's confidence and window are enough to judge at all.
        Call it for every reading in clock order, whether or not it is over the threshold: the
        quiet ones are how a shift is seen to end.
        """
        series = (reading.signal, reading.team)
        size = abs(reading.z_match)
        if not trusted or size < settings.spotter_z_release:
            self._direction.pop(series, None)
            return False
        if size < settings.spotter_z_threshold:
            return False  # between release and threshold: the same shift, or none at all
        direction = 1 if reading.z_match > 0 else -1
        if self._direction.get(series) == direction:
            return False
        self._direction[series] = direction
        key = (*series, MomentType.TACTICAL_SHIFT)
        last = self._fired_at_ms.get(key)
        if last is not None and reading.clock_ms - last < settings.spotter_cooldown_ms:
            return False
        self._fired_at_ms[key] = reading.clock_ms
        return True
