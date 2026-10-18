"""Produces structured claims for a moment from a log frozen at that clock"""

from collections.abc import Sequence

from matchlens import calltrace
from matchlens.models import Claim, ClaimType, Event, Moment, Operand, Ref, RefKind, Window


def explain(moment: Moment, frozen_log: Sequence[Event]) -> list[Claim]:
    """Claims about `moment`, read only from the frozen log.

    Stub until A2: one fixed descriptive claim, that the events which fired the moment happened
    at its clock. It cites those events, so it passes through the same path a real claim will.
    """
    calltrace.entered("Explanation")
    triggers = tuple(Ref(kind=RefKind.EVENT, id=e) for e in moment.trigger_event_ids)
    if not triggers:
        return []  # nothing to cite, so no claim (invariant 5)
    operand = Operand(
        subject=moment.subject,
        metric="trigger_events",
        window=Window(start_ms=moment.clock_ms, end_ms=moment.clock_ms),
        value=float(len(triggers)),
        evidence_ids=triggers,
    )
    return [
        Claim(
            claim_id=f"{moment.moment_id}:c1",
            moment_id=moment.moment_id,
            claim_type=ClaimType.DESCRIPTIVE,
            operands=(operand,),
            backing_reading=None,
            threshold=None,
            model="stub",
            model_version="S4",
        )
    ]
