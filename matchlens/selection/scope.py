"""How a lens's scope judges a moment's importance: two mechanisms, not one filter (D2).

`match` applies no subject logic. `team` reweights: it keeps the moments about the opponent,
because an opponent goal is the most important thing that can happen to a supporter, and it
boosts what moves the result and damps a tactical shift by the supporter's own side. `player`
is a hard subject filter, deferred with `Run` (D1).
"""

from matchlens.config import settings
from matchlens.models import Lens, Moment, MomentType, Ref, RefKind, Scope

_MOVES_THE_RESULT = frozenset({MomentType.GOAL, MomentType.CHANCE})


def judged_importance(moment: Moment, lens: Lens) -> float:
    """The importance this lens judges `moment` at, before its threshold applies."""
    match lens.scope:
        case Scope.MATCH:
            return _match(moment)
        case Scope.TEAM:
            return _team(moment, lens)
        case Scope.PLAYER:
            raise NotImplementedError("player scope is deferred (D1); it needs Run")


def _match(moment: Moment) -> float:
    return moment.importance


def _team(moment: Moment, lens: Lens) -> float:
    if moment.type in _MOVES_THE_RESULT:
        return min(1.0, moment.importance * settings.team_result_boost)
    # A shift by the opponent is left alone: it may be happening to the supporter's side.
    if moment.type is MomentType.TACTICAL_SHIFT and moment.subject == _focus(lens):
        return moment.importance * settings.team_focus_shift_damp
    return moment.importance


def _focus(lens: Lens) -> Ref:
    assert lens.focus_team is not None  # Lens requires it for team scope
    return Ref(kind=RefKind.TEAM, id=lens.focus_team)
