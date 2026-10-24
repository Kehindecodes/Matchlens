"""Produces structured claims for a moment from a log frozen at that clock"""

from collections.abc import Sequence

from matchlens import calltrace
from matchlens.explanation import agent
from matchlens.explanation.agent import Answer, Proposer
from matchlens.explanation.builder import MODEL, explain_moment
from matchlens.ingest import FrozenLog
from matchlens.models import Claim, Moment

__all__ = ["Answer", "Proposer", "by_rule", "explain"]


def explain(moment: Moment, log: FrozenLog, proposer: Proposer | None = None) -> list[Claim]:
    """Claims about `moment`, read only from `log`, which is frozen at the moment's clock.

    L7's claims, built by rule from the frozen log and the readings with no model, then any the
    model behind `proposer` adds to them (A2, D35). With no proposer, or one that fails, the
    claims are L7's alone. The log cannot serve anything after its clock (invariant 6), and
    nothing on it can reach a frame (invariant 1). A claim with nothing to cite is not made
    (invariant 5).

    Raises `ValueError` for a log frozen at another clock: a later one would hold the future.
    """
    calltrace.entered("Explanation")
    if log.clock_ms != moment.clock_ms:
        raise ValueError(
            f"log frozen at {log.clock_ms} ms, moment {moment.moment_id} is at {moment.clock_ms} ms"
        )
    claims = explain_moment(moment, log.events, log.readings, log.epochs, log.match)
    if proposer is not None:
        claims += agent.propose(moment, log, claims, proposer)
    return claims


def by_rule(claims: Sequence[Claim]) -> list[Claim]:
    """The claims L7 built, without any a model proposed."""
    return [c for c in claims if c.model == MODEL]
