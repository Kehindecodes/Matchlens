"""Chooses which verified claims one lens shows"""

from collections.abc import Sequence

from matchlens.models import Claim, Lens, Moment


def select(moment: Moment, claims: Sequence[Claim], lens: Lens) -> list[Claim]:
    """The subset of `claims` this lens shows, chosen without a model call. Stub: L2."""
    raise NotImplementedError("selection lands in L2")
