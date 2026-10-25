"""Who was on the pitch when: derived from the roster and the event log, never stored (D16).

A player enters at kickoff if he started, or on the substitution that brings him on, and leaves
on the substitution taking him off or his red card. On the pitch at `c` means
`entered <= c < left`. Because the log is append-only, deriving this again later always gives
the same answer, so a claim checked again after the match is judged as it was live.
"""

from collections.abc import Iterable

from matchlens.models import Action, Event, Player

_NEVER = 2**62  # past any match clock: not entered, or not left yet


def pitch_window(player: Player, events: Iterable[Event]) -> tuple[int, int]:
    """`(entered, left)` for `player` over `events`; `entered` is `_NEVER` if he never came on."""
    entered = 0 if player.is_starter else _NEVER
    left = _NEVER
    for e in events:
        if e.action is Action.SUBSTITUTION and e.player_on == player.player_id:
            entered = min(entered, e.clock_ms)
        elif e.action in (Action.SUBSTITUTION, Action.RED_CARD) and e.player == player.player_id:
            left = min(left, e.clock_ms)
    return entered, left


def on_pitch_across(player: Player, events: Iterable[Event], start_ms: int, end_ms: int) -> bool:
    """Whether `player` was on the pitch at every clock from `start_ms` to `end_ms`."""
    entered, left = pitch_window(player, events)
    return entered <= start_ms and end_ms < left
