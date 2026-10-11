"""Turns one lens's selected claims into a rendition"""

from collections.abc import Sequence

from matchlens.models import Claim, Lens, Moment, Rendition


def render(moment: Moment, selected: Sequence[Claim], lens: Lens) -> Rendition:
    """One rendition of `moment` for `lens`, suppressed or shown. Stub: L3 implements it."""
    raise NotImplementedError("rendering lands in L3")
