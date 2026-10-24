"""Produces structured claims for a moment from a log frozen at that clock"""

from matchlens import calltrace
from matchlens.explanation.builder import explain_moment
from matchlens.ingest import FrozenLog
from matchlens.models import Claim, Moment

__all__ = ["explain"]


def explain(moment: Moment, log: FrozenLog) -> list[Claim]:
    """Claims about `moment`, read only from `log`, which is frozen at the moment's clock.

    The L1 explainer (L7): D30's claims built by rule from the frozen log and the readings, with
    no model. The log cannot serve anything after its clock (invariant 6), and nothing on it can
    reach a frame (invariant 1). A claim with nothing to cite is not made (invariant 5).

    Raises `ValueError` for a log frozen at another clock: a later one would hold the future.
    """
    calltrace.entered("Explanation")
    if log.clock_ms != moment.clock_ms:
        raise ValueError(
            f"log frozen at {log.clock_ms} ms, moment {moment.moment_id} is at {moment.clock_ms} ms"
        )
    return explain_moment(moment, log.events, log.readings, log.epochs, log.match)
