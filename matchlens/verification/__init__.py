"""Checks each claim against the untouched record and returns a verdict"""

from collections.abc import Sequence

from matchlens import calltrace
from matchlens.models import Claim, Event, Verification


def verify(claim: Claim, record: Sequence[Event]) -> Verification:
    """The verdict on one claim. Stub: A3 implements it, against the `Claim` schema."""
    calltrace.entered("Verification")
    raise NotImplementedError("verification lands in A3")
