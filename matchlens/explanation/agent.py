"""A2: a model proposing claims on top of L7's, in the same schema and vocabulary (D35).

The model is shown a digest of the frozen log and the claims L7 already made, and answers with
claims in JSON. Its answer is parsed into `Claim`s, and the pydantic validators are the gate:
an answer that does not parse, or breaks a rule below, is a failure to report, not something
to repair, and gives no claims at all. A claim whose evidence is not in the frozen log has
nothing citable and is dropped on its own (invariant 5).

Additive: an A2 that answers nothing, badly or late leaves L7's claims exactly as they were.
"""

import json
import logging
from collections.abc import Sequence
from typing import NamedTuple, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from matchlens.config import settings
from matchlens.ingest import FrozenLog
from matchlens.models import (
    Claim,
    ClaimType,
    Metric,
    Moment,
    Operand,
    Ref,
    RefKind,
)
from matchlens.understanding.possession import from_events
from matchlens.understanding.shot_value import is_shot, value

logger = logging.getLogger(__name__)

PROMPT_VERSION = "explainer-1"  # bump by hand whenever the instructions or the digest change


class Answer(NamedTuple):
    """What a model said, and which model said it (invariant 7)."""

    text: str
    model: str
    model_version: str


class Proposer(Protocol):
    def propose(self, instructions: str, prompt: str) -> Answer:
        """The model's answer to `prompt`. Raises on a failed or timed-out call."""
        ...


class NonConforming(ValueError):
    """An answer that parsed but broke a rule the schema cannot state."""


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _Proposed(_Strict):
    """One claim as the model writes it: a `Claim` without the ids A2 gives it."""

    claim_type: ClaimType
    operands: tuple[Operand, ...]
    backing_reading: Ref | None
    threshold: float | None


class _Response(_Strict):
    claims: tuple[_Proposed, ...]


INSTRUCTIONS = f"""\
You propose additional structured claims about one moment of a football match. You never write
prose. You read only the JSON you are given, which holds everything up to the moment's clock.

Answer with one JSON object and nothing else: {{"claims": [...]}}. An empty list is a good
answer when nothing worth adding is there. Each claim is:
  {{"claim_type": "descriptive" | "comparative" | "interpretive",
    "operands": [operand, ...],
    "backing_reading": null | {{"kind": "reading", "id": "<reading_id>"}},
    "threshold": null | number}}
and each operand is:
  {{"subject": {{"kind": "team" | "player", "id": "<id>"}},
    "metric": one of {sorted(m.value for m in Metric)},
    "window": {{"start_ms": int, "end_ms": int}},
    "value": number,
    "evidence_ids": [{{"kind": "event" | "reading", "id": "<id>"}}, ...]}}

Rules. A claim that breaks one is worthless, and an answer that breaks one is thrown away whole.
- descriptive and interpretive claims have one operand; comparative claims have two.
- A comparative claim compares the same metric for a different subject or a different window:
  the same team in the previous epoch, or the opponent over the same window. Never restate the
  first operand as the second.
- Only an interpretive claim has backing_reading and threshold. It interprets a signal reading:
  backing_reading is that reading, and threshold is the z_match its wording implies, signed:
  +{settings.spotter_z_threshold} or -{settings.spotter_z_threshold} for plain words,
  +{settings.claim_strong_z} or -{settings.claim_strong_z} for strong ones.
- Every value must be recountable from the rows its evidence_ids cite, and only from them:
  goals counts goal events; chances counts shots with shot_quality of at least
  {settings.spotter_chance_quality}; shot_quality is one shot's shot_quality; build_up_passes
  counts the passes in one possession; territory, possession_control, pressing_intensity and
  chance_quality are the value of the one reading cited.
- Cite only ids that appear in the JSON. Do not repeat a claim already in existing_claims.
"""


def digest(moment: Moment, log: FrozenLog, made: Sequence[Claim]) -> str:
    """What the model is shown: built from `log` alone, so nothing after its clock is in it."""
    match = log.match
    recent = moment.clock_ms - settings.explainer_recent_ms
    latest: dict[tuple[str, str, str], dict[str, object]] = {}
    for r in log.readings:  # the last reading of each series in each epoch
        latest[(r.signal.value, r.team, r.epoch_id)] = {
            "reading_id": r.reading_id,
            "signal": r.signal.value,
            "team": r.team,
            "clock_ms": r.clock_ms,
            "window_ms": r.window_ms,
            "value": r.value,
            "z_match": r.z_match,
            "epoch_id": r.epoch_id,
        }
    return json.dumps(
        {
            "moment": moment.model_dump(
                mode="json", include={"moment_id", "clock_ms", "type", "subject", "epoch_id"}
            )
            | {"triggers": [*moment.trigger_event_ids, *moment.trigger_reading_ids]},
            "teams": [{"team_id": t.team_id, "name": t.name} for t in match.teams],
            "epochs": [e.model_dump(mode="json") for e in log.epochs],
            "shots": [
                {
                    "event_id": e.event_id,
                    "clock_ms": e.clock_ms,
                    "team": e.team,
                    "player": e.player,
                    "outcome": e.outcome.value if e.outcome is not None else None,
                    "shot_quality": value(e, match).value,
                }
                for e in log.events
                if is_shot(e)
            ],
            "possessions": [
                {
                    "team": p.team,
                    "start_clock_ms": p.start_clock_ms,
                    "end_clock_ms": p.end_clock_ms,
                    "pass_count": p.pass_count,
                    "event_ids": list(p.event_ids),
                }
                for p in from_events(match, log.events)
                if p.end_clock_ms >= recent
            ],
            "readings": list(latest.values()),
            "existing_claims": [
                c.model_dump(mode="json", exclude={"claim_id", "moment_id", "model"}) for c in made
            ],
        },
        separators=(",", ":"),
    )


def propose(
    moment: Moment, log: FrozenLog, made: Sequence[Claim], proposer: Proposer
) -> list[Claim]:
    """The claims the model adds to `made`, or none if it failed, timed out or did not conform."""
    try:
        answer = proposer.propose(INSTRUCTIONS, digest(moment, log, made))
    except Exception as failure:  # any failure to answer is the same failure: no claims
        logger.warning("explainer: no answer for %s: %r", moment.moment_id, failure)
        return []
    try:
        response = _Response.model_validate_json(answer.text, strict=True)
        claims = [
            Claim(
                claim_id=f"{moment.moment_id}:a{n}",
                moment_id=moment.moment_id,
                model=answer.model,
                model_version=f"{answer.model_version}+{PROMPT_VERSION}",
                **dict(proposed),
            )
            for n, proposed in enumerate(response.claims, start=1)
        ]
        for claim in claims:
            _conforms(claim)
    except (ValidationError, NonConforming) as failure:
        logger.warning(
            "explainer: non-conforming answer for %s from %s %s: %s",
            moment.moment_id,
            answer.model,
            answer.model_version,
            failure,
        )
        return []
    return [c for c in claims if _citable(c, log) and not _restates(c, made)]


def _conforms(claim: Claim) -> None:
    """The rules D21 and D30 set that `Claim`'s own validators do not."""
    if claim.claim_type is ClaimType.COMPARATIVE:
        first, second = claim.operands
        if first.metric is not second.metric:
            raise NonConforming(f"{claim.claim_id} compares {first.metric} with {second.metric}")
        if (first.subject, first.window) == (second.subject, second.window):
            raise NonConforming(f"{claim.claim_id} compares an operand with itself")
        if first.evidence_ids == second.evidence_ids:
            raise NonConforming(f"{claim.claim_id}'s two operands cite the same evidence")
    if claim.threshold is not None:
        bands = {settings.spotter_z_threshold, settings.claim_strong_z}
        if abs(claim.threshold) not in bands:
            raise NonConforming(f"{claim.claim_id}'s threshold {claim.threshold} is no band")


def _citable(claim: Claim, log: FrozenLog) -> bool:
    """Whether every ref the claim cites is a row in the frozen log (invariant 5)."""
    events = {e.event_id for e in log.events}
    readings = {r.reading_id for r in log.readings}
    known = {RefKind.EVENT: events, RefKind.READING: readings}
    refs = [ref for o in claim.operands for ref in o.evidence_ids]
    if claim.backing_reading is not None:
        refs.append(claim.backing_reading)
    missing = [ref for ref in refs if ref.id not in known.get(ref.kind, set())]
    if missing:
        logger.warning("explainer: dropped %s, which cites %s", claim.claim_id, missing)
    return not missing


def _restates(claim: Claim, made: Sequence[Claim]) -> bool:
    return any(
        (c.claim_type, c.operands, c.threshold)
        == (claim.claim_type, claim.operands, claim.threshold)
        for c in made
    )
