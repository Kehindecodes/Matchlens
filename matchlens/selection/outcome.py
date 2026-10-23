"""What Selection hands to Rendering: the claims a lens shows, or the one reason it shows none.

`ShownCards` is the only state Selection keeps. It belongs to one match, so two matches in one
process cannot rate-limit each other, and it counts on the match clock, never the wall clock.
"""

from dataclasses import dataclass, field

from matchlens.models import Claim, SuppressionReason

TEN_MINUTES_MS = 600_000


@dataclass(frozen=True)
class Selection:
    """The claims one lens shows for one moment, or why it shows none (invariant 11).

    `importance` is what the lens judged the moment at, after its scope's reweight.
    """

    claims: tuple[Claim, ...]
    suppression_reason: SuppressionReason | None
    importance: float

    def __post_init__(self) -> None:
        if bool(self.claims) == (self.suppression_reason is not None):
            raise ValueError("a selection has claims or exactly one suppression reason, not both")


@dataclass
class ShownCards:
    """The match clock of every card each lens has shown, for one match."""

    _clocks: dict[str, list[int]] = field(default_factory=dict)

    def record(self, lens_id: str, clock_ms: int) -> None:
        self._clocks.setdefault(lens_id, []).append(clock_ms)

    def in_window(self, lens_id: str, clock_ms: int) -> int:
        """How many cards the lens showed in the ten match minutes ending at `clock_ms`."""
        return sum(
            clock_ms - TEN_MINUTES_MS < shown <= clock_ms for shown in self._clocks.get(lens_id, ())
        )
