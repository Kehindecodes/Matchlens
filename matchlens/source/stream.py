"""What the Match Source yields.

The roster is a pre-match setup message, not an event: events reference players and teams by id,
so it must land before the first frame or event (D16). It carries no `seq`; `seq` orders the
frame and event stream that follows it.
"""

from pydantic import BaseModel, ConfigDict

from matchlens.models import Event, Frame, Match, Player


class MatchSetup(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    match: Match
    players: tuple[Player, ...]


StreamItem = MatchSetup | Frame | Event
