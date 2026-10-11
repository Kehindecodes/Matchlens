"""Selects and renders the surviving claim set for one lens"""

from collections.abc import Sequence

from matchlens.models import Claim, Lens, Moment, Rendition


def render(moment: Moment, claims: Sequence[Claim], lens: Lens) -> Rendition:
    """One rendition of `moment` for `lens`, suppressed or shown. Stub: L2 implements it."""
    raise NotImplementedError("rendering lands in L2")
