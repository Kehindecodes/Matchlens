"""Produces structured claims for a moment from a log frozen at that clock"""

from collections.abc import Sequence

from matchlens import calltrace
from matchlens.explanation.builder import explain_moment
from matchlens.models import Claim, Epoch, Event, Match, Moment, SignalReading

__all__ = ["explain"]


def explain(
    moment: Moment,
    frozen_log: Sequence[Event],
    readings: Sequence[SignalReading],
    epochs: Sequence[Epoch],
    match: Match,
) -> list[Claim]:
    """Claims about `moment`, read only from what had happened by its clock.

    The L1 explainer (L7): D30's claims built by rule from the frozen log and the readings, with
    no model. Nothing after `moment.clock_ms` is read, whatever the caller passes (invariant 6),
    and no input can reach a frame (invariant 1). A claim with nothing to cite is not made
    (invariant 5).
    """
    calltrace.entered("Explanation")
    clock = moment.clock_ms
    return explain_moment(
        moment,
        [e for e in frozen_log if e.clock_ms <= clock],
        [r for r in readings if r.clock_ms <= clock],
        [e for e in epochs if e.start_clock_ms <= clock],
        match,
    )
