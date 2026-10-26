"""Chooses which verified claims one lens shows"""

from collections.abc import Sequence

from matchlens import calltrace
from matchlens.models import Claim, Lens, Moment, SuppressionReason
from matchlens.selection.outcome import Selection, ShownCards
from matchlens.selection.scope import judged_importance

__all__ = ["Selection", "ShownCards", "select"]


def select(
    moment: Moment,
    claims: Sequence[Claim],
    lens: Lens,
    shown: ShownCards,
    *,
    muted: bool = False,
) -> Selection:
    """The claims `lens` shows for `moment`, or the one reason it shows none.

    `claims` are the ones that passed verification. No model is called, and nothing is written
    except the card this lens now counts against its rate limit, in `shown`, which belongs to
    one match.

    `muted` is Control's decision, made before Selection runs (P2). It outranks every reason
    below, as DATA-MODEL's order has it, and a muted lens spends none of its rate limit.

    Every reason that applies is weighed and the first in `SuppressionReason`'s declared order
    wins (D14), so the answer does not depend on which check runs first:

    1. scope: the importance this lens judges the moment at. Neither path in use puts a moment
       out of scope, so `out_of_scope` is not produced in v1.
    2. no verified claims: `verification_failed`
    3. claim types: `claims_filtered_out`, when this lens allows none of the claims
    4. threshold: `below_threshold`
    5. rate limit: `rate_limited`, unless the moment's type is one of the lens's
       `breakthrough_types`. Those are still counted.

    `degraded` belongs to the ladder, which decides before Selection runs.
    """
    calltrace.entered("Selection")
    importance = judged_importance(moment, lens)
    if muted:
        return Selection(
            claims=(), suppression_reason=SuppressionReason.MUTED, importance=importance
        )

    reason = None
    kept = tuple(c for c in claims if c.claim_type in lens.allowed_claim_types)
    if not claims:
        reason = SuppressionReason.VERIFICATION_FAILED
    elif not kept:
        reason = SuppressionReason.CLAIMS_FILTERED_OUT
    elif importance < lens.importance_threshold:
        reason = SuppressionReason.BELOW_THRESHOLD
    elif (
        moment.type not in lens.breakthrough_types
        and shown.in_window(lens.lens_id, moment.clock_ms) >= lens.max_cards_per_10min
    ):
        reason = SuppressionReason.RATE_LIMITED

    if reason is not None:
        return Selection(claims=(), suppression_reason=reason, importance=importance)
    shown.record(lens.lens_id, moment.clock_ms)
    return Selection(claims=kept, suppression_reason=None, importance=importance)
