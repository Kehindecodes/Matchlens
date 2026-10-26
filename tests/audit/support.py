"""What the Audit tests share: real claims from seed 1, verified by the real verifier.

Nothing here is a stand-in for A3. A rejected claim is a real L7 claim with one number changed,
and its verdict is whatever `verification.verify` says about it.
"""

from matchlens import verification
from matchlens.models import Claim, Verification
from tests.verification.test_verify import Explained, Played, _goal, _with_operand


def verify_all(explained: Explained, claims: list[Claim] | None = None) -> list[Verification]:
    """Every claim of the moment verified the way the pipeline does it, against its own record."""
    claims = explained.claims if claims is None else claims
    return [
        verification.verify(claim, explained.moment, claims, explained.record) for claim in claims
    ]


def with_wrong_value(claim: Claim, by: float = 1.0) -> Claim:
    """A new claim that says the first operand's value is `by` more than it is."""
    wrong = _with_operand(claim, 0, value=claim.operands[0].value + by)
    return wrong.model_copy(update={"claim_id": f"{claim.claim_id}-wrong"})


def a_moment_with_a_wrong_claim(played: Played) -> tuple[Explained, list[Claim]]:
    """The first goal of the match, and its claims with one more that has the wrong value."""
    goal = _goal(played)
    return goal, [*goal.claims, with_wrong_value(goal.claims[0])]


def a_moment_with_claims(played: Played, after: int = 0) -> Explained:
    """The first moment with claims, or the first of those after the `after`-th moment."""
    return next(explained for explained in played.explained[after:] if explained.claims)
