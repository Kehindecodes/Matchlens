"""Chooses which verified claims one lens shows"""

from collections.abc import Sequence

from matchlens import calltrace
from matchlens.models import Claim, Lens, Moment


def select(moment: Moment, claims: Sequence[Claim], lens: Lens) -> list[Claim]:
    """The subset of `claims` this lens shows, chosen without a model call. Stub: all, until L2."""
    calltrace.entered("Selection")
    return list(claims)
