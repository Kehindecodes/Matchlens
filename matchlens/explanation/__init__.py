"""Produces structured claims for a moment from a log frozen at that clock"""

from collections.abc import Sequence

from matchlens import calltrace
from matchlens.models import Claim, Event, Moment


def explain(moment: Moment, frozen_log: Sequence[Event]) -> list[Claim]:
    """Claims about `moment`, read only from events before its clock. Stub: no claims until A2."""
    calltrace.entered("Explanation")
    return []
