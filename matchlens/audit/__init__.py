"""Records what was said and how it held up"""

from collections.abc import Sequence

from matchlens import calltrace
from matchlens.models import Claim, Moment, Rendition, Verification


def record(
    moment: Moment,
    claims: Sequence[Claim],
    verifications: Sequence[Verification],
    renditions: Sequence[Rendition],
) -> None:
    """Keep one moment's full trail for the post-match report. Stub: keeps nothing yet."""
    calltrace.entered("Audit")
