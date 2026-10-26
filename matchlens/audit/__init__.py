"""Records what was said and how it held up"""

import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from matchlens import calltrace
from matchlens.models import Claim, Moment, Rendition, Verification

__all__ = ["AlreadyRecorded", "Audit", "Audited", "Unverified"]


class AlreadyRecorded(ValueError):
    """A moment's trail was recorded a second time. The first stands (invariant 2)."""


class Unverified(ValueError):
    """A claim came with no verdict. A claim without one counts as failed (invariant 5)."""


@dataclass(frozen=True)
class Audited:
    """One moment's trail: what was said, how each claim held up, and what each lens did with it."""

    moment: Moment
    claims: tuple[Claim, ...]
    verifications: tuple[Verification, ...]
    renditions: tuple[Rendition, ...]


class Audit:
    """The trail of every moment so far, in memory and append-only (P3, Q45: 1B).

    The pipeline writes one entry per moment as it finishes with it, on its editorial thread; the
    views read. Nothing is edited or removed once recorded, and a frame never reaches it
    (invariant 1): it is handed claims, verdicts and renditions, which cite frames and do not
    hold them. In memory because v1 has no database (D38); a durable one goes behind this same
    interface.
    """

    def __init__(self) -> None:
        self._trail: list[Audited] = []
        self._recorded: set[str] = set()
        self._names: dict[str, str] = {}
        self._lock = threading.Lock()

    def record(
        self,
        moment: Moment,
        claims: Sequence[Claim],
        verifications: Sequence[Verification],
        renditions: Sequence[Rendition],
    ) -> None:
        """Keep one moment's full trail. A moment is recorded once, and every claim of it must
        come with its verdict."""
        calltrace.entered("Audit")
        judged = {verification.claim_id for verification in verifications}
        unjudged = [claim.claim_id for claim in claims if claim.claim_id not in judged]
        if unjudged:
            raise Unverified(f"{moment.moment_id}: no verdict for {', '.join(unjudged)}")
        entry = Audited(moment, tuple(claims), tuple(verifications), tuple(renditions))
        with self._lock:
            if moment.moment_id in self._recorded:
                raise AlreadyRecorded(moment.moment_id)
            self._recorded.add(moment.moment_id)
            self._trail.append(entry)

    def trail(self, after: int = 0) -> tuple[Audited, ...]:
        """The moments recorded so far in the order they were, from the `after`-th on."""
        with self._lock:
            return tuple(self._trail[max(0, after) :])

    def introduce(self, names: Mapping[str, str]) -> None:
        """Take the names of the match's teams and players, by id, so a view can label them."""
        with self._lock:
            self._names |= names

    @property
    def names(self) -> dict[str, str]:
        with self._lock:
            return dict(self._names)
