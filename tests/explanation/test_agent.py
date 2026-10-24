"""A2: a model's claims, on top of L7's, in the same schema and vocabulary (D35).

There is no live model yet (Q33: B), so the models here are scripted. `Honest` reads the digest
it is shown and claims only what that digest supports, so its claims are what a model that
follows the instructions would write. The others fail in the ways a real one does.
"""

import json
import logging
import threading
from typing import override

import pytest

from apps import pipeline
from matchlens import explanation
from matchlens.explanation import Answer, Proposer, agent
from matchlens.models import Claim, ClaimType, Metric
from matchlens.source import simulate
from tests.explanation.test_builder import Played, _play, _recount

MODEL, VERSION = "fake-model", "fake-1"


def _ref(kind: str, id_: str) -> dict[str, str]:
    return {"kind": kind, "id": id_}


def _reading_operand(r: dict) -> dict:
    return {
        "subject": _ref("team", r["team"]),
        "metric": r["signal"],
        "window": {"start_ms": r["clock_ms"] - r["window_ms"], "end_ms": r["clock_ms"]},
        "value": r["value"],
        "evidence_ids": [_ref("reading", r["reading_id"])],
    }


def _honest(prompt: str) -> list[dict]:
    """Claims a model following the instructions could make from `prompt`, and nothing else.

    It reads the readings that did not fire the moment, since L7 already claims the one that
    did, and a restated claim is dropped.
    """
    d = json.loads(prompt)
    moment, teams = d["moment"], [t["team_id"] for t in d["teams"]]
    claims = []
    now = [
        r
        for r in d["readings"]
        if r["epoch_id"] == moment["epoch_id"] and r["reading_id"] not in moment["triggers"]
    ]
    if moment["subject"]["id"] in teams:
        mine = [r for r in now if r["team"] == moment["subject"]["id"]]
        for r in mine[:1]:
            theirs = [
                x
                for x in now
                if x["team"] != r["team"]
                and x["signal"] == r["signal"]
                and x["clock_ms"] == r["clock_ms"]
            ]
            if theirs:
                claims.append(
                    {
                        "claim_type": "comparative",
                        "operands": [_reading_operand(r), _reading_operand(theirs[0])],
                        "backing_reading": None,
                        "threshold": None,
                    }
                )
    for r in [r for r in now if abs(r["z_match"]) >= 1.25][:1]:
        band = 2.0 if abs(r["z_match"]) >= 2.0 else 1.25
        claims.append(
            {
                "claim_type": "interpretive",
                "operands": [_reading_operand(r)],
                "backing_reading": _ref("reading", r["reading_id"]),
                "threshold": band if r["z_match"] > 0 else -band,
            }
        )
    if d["shots"]:
        shot = d["shots"][-1]
        claims.append(
            {
                "claim_type": "descriptive",
                "operands": [
                    {
                        "subject": _ref("team", shot["team"]),
                        "metric": "shot_quality",
                        "window": {"start_ms": shot["clock_ms"], "end_ms": shot["clock_ms"]},
                        "value": shot["shot_quality"],
                        "evidence_ids": [_ref("event", shot["event_id"])],
                    }
                ],
                "backing_reading": None,
                "threshold": None,
            }
        )
    return claims


class Honest(Proposer):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        self.prompts.append(prompt)
        return Answer(json.dumps({"claims": _honest(prompt)}), MODEL, VERSION)


class Liar(Proposer):
    """Honest about everything except the numbers."""

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        claims = _honest(prompt)
        for claim in claims:
            for operand in claim["operands"]:
                operand["value"] += 1.0
        return Answer(json.dumps({"claims": claims}), MODEL, VERSION)


class Says(Proposer):
    def __init__(self, text: str):
        self.text = text

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        return Answer(self.text, MODEL, VERSION)


class Fails(Proposer):
    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        raise TimeoutError("no answer in time")


def _proposed(played: Played) -> list[Claim]:
    return [c for x in played.explained for c in x.claims if c.model != "deterministic"]


@pytest.fixture(scope="module")
def honest() -> tuple[Played, Honest]:
    model = Honest()
    return _play(1, proposer=model), model


# --- what an A2 claim is -------------------------------------------------------------------------


def test_every_claim_a2_emits_is_a_claim_in_d30s_metrics(honest):
    played, _ = honest
    proposed = _proposed(played)
    assert proposed
    assert {c.claim_type for c in proposed} == set(ClaimType)  # every shape was exercised
    for claim in proposed:
        assert isinstance(claim, Claim)
        assert all(isinstance(o.metric, Metric) for o in claim.operands)


def test_every_value_a2_claims_recomputes_from_its_cited_evidence(honest):
    # The contract with A3: a model that follows the instructions makes claims A3 will pass.
    played, _ = honest
    for claim in _proposed(played):
        for operand in claim.operands:
            assert _recount(operand, played) == pytest.approx(operand.value), claim.claim_id


def test_a2s_claims_come_after_l7s_and_l7s_are_untouched(honest):
    played, _ = honest
    alone = _play(1)
    for with_model, without in zip(played.explained, alone.explained, strict=True):
        assert explanation.by_rule(with_model.claims) == without.claims
        rule = len(without.claims)
        assert all(c.model == MODEL for c in with_model.claims[rule:])


def test_a_comparison_has_a_real_second_operand(honest):
    played, _ = honest
    comparisons = [c for c in _proposed(played) if c.claim_type is ClaimType.COMPARATIVE]
    assert comparisons
    for claim in comparisons:
        first, second = claim.operands
        assert first.metric is second.metric
        assert (first.subject, first.window) != (second.subject, second.window)
        assert first.evidence_ids != second.evidence_ids


def test_an_interpretive_threshold_is_signed_and_in_a_band(honest):
    played, _ = honest
    interpretive = [c for c in _proposed(played) if c.claim_type is ClaimType.INTERPRETIVE]
    assert interpretive
    for claim in interpretive:
        assert claim.threshold is not None and claim.backing_reading is not None
        assert abs(claim.threshold) in {1.25, 2.0}
        fired = played.readings[claim.backing_reading.id]
        assert (claim.threshold > 0) == (fired.z_match > 0)


def test_every_a2_claim_says_which_model_and_prompt_made_it(honest):
    played, _ = honest
    for claim in _proposed(played):
        assert claim.model == MODEL
        assert claim.model_version == f"{VERSION}+{agent.PROMPT_VERSION}"
        assert claim.claim_id.startswith(f"{claim.moment_id}:a")


def test_the_model_never_sees_past_the_moments_clock(honest):
    # A1's poisoned log, on A2's path: every frozen log is built from the finished match, and
    # the model must be shown byte for byte what it was shown live.
    played, live = honest
    poisoned = Honest()
    _play(1, poison=played, proposer=poisoned)
    assert poisoned.prompts == live.prompts


# --- what A2 refuses -----------------------------------------------------------------------------


def _one_moment(seed_1_honest: Played):
    x = seed_1_honest.explained[0]
    log = next(log for log in seed_1_honest.logs if log.clock_ms == x.moment.clock_ms)
    rule = explanation.by_rule(x.claims)
    return x.moment, log, rule


def _good(seed_1_honest: Played) -> dict:
    moment, log, rule = _one_moment(seed_1_honest)
    [claim, *_] = _honest(agent.digest(moment, log, rule))
    return claim


def _with(claim: dict, **changes) -> dict:
    return json.loads(json.dumps(claim)) | changes


def _operand(claim: dict, **changes) -> dict:
    return json.loads(json.dumps(claim["operands"][0])) | changes


NON_CONFORMING = {
    "not JSON": lambda good: "The home side pressed hard.",
    "no claims key": lambda good: json.dumps({"proposals": [good]}),
    "an invented metric": lambda good: json.dumps(
        {"claims": [_with(good, operands=[_operand(good, metric="momentum")] * 2)]}
    ),
    "a field the schema does not have": lambda good: json.dumps(
        {"claims": [_with(good, confidence=0.9)]}
    ),
    "a number written as a string": lambda good: json.dumps(
        {"claims": [_with(good, operands=[_operand(good, value="0.5")] * 2)]}
    ),
    "a comparison with one operand": lambda good: json.dumps(
        {"claims": [_with(good, operands=good["operands"][:1])]}
    ),
    "a comparison restating its first operand": lambda good: json.dumps(
        {"claims": [_with(good, operands=[good["operands"][0]] * 2)]}
    ),
    "a comparison across two metrics": lambda good: json.dumps(
        {"claims": [_with(good, operands=[good["operands"][0], _operand(good, metric="goals")])]}
    ),
    "a descriptive claim with a threshold": lambda good: json.dumps(
        {
            "claims": [
                _with(good, claim_type="descriptive", operands=good["operands"][:1], threshold=1.25)
            ]
        }  # fmt: skip
    ),
    "an interpretive claim with no backing": lambda good: json.dumps(
        {
            "claims": [
                _with(
                    good, claim_type="interpretive", operands=good["operands"][:1], threshold=1.25
                )
            ]
        }  # fmt: skip
    ),
    "a threshold that is no band": lambda good: json.dumps(
        {
            "claims": [
                _with(
                    good,
                    claim_type="interpretive",
                    operands=good["operands"][:1],
                    backing_reading=good["operands"][0]["evidence_ids"][0],
                    threshold=1.7,
                )
            ]
        }
    ),
    "one good claim and one bad": lambda good: json.dumps(
        {"claims": [good, _with(good, operands=good["operands"][:1])]}
    ),
}


@pytest.mark.parametrize("case", NON_CONFORMING)
def test_a_non_conforming_answer_gives_no_claims_and_is_logged(case, honest, caplog):
    played, _ = honest
    good = _good(played)
    assert good["claim_type"] == "comparative"  # the cases above are written against one
    moment, log, rule = _one_moment(played)
    with caplog.at_level(logging.WARNING, logger=agent.__name__):
        claims = explanation.explain(moment, log, Says(NON_CONFORMING[case](good)))
    assert claims == rule
    assert any("non-conforming" in r.message for r in caplog.records), caplog.text


def test_the_good_claim_those_cases_are_built_from_is_accepted(honest):
    played, _ = honest
    moment, log, rule = _one_moment(played)
    claims = explanation.explain(moment, log, Says(json.dumps({"claims": [_good(played)]})))
    assert len(claims) == len(rule) + 1


def test_a_claim_citing_a_row_not_in_the_log_is_dropped_alone(honest, caplog):
    played, _ = honest
    moment, log, rule = _one_moment(played)
    good = _good(played)
    second = good["operands"][1] | {"evidence_ids": [_ref("reading", "r-invented")]}
    invented = _with(good, operands=[good["operands"][0], second])
    answer = json.dumps({"claims": [invented, good]})
    with caplog.at_level(logging.WARNING, logger=agent.__name__):
        claims = explanation.explain(moment, log, Says(answer))
    assert [c.claim_id for c in claims[len(rule) :]] == [f"{moment.moment_id}:a2"]
    assert any("r-invented" in r.message for r in caplog.records)


def test_a_claim_l7_already_made_is_not_made_twice(honest):
    played, _ = honest
    moment, log, rule = _one_moment(played)
    again = rule[0].model_dump(mode="json", include={"claim_type", "operands", "backing_reading",
                                                     "threshold"})  # fmt: skip
    assert explanation.explain(moment, log, Says(json.dumps({"claims": [again]}))) == rule


def test_a_model_that_fails_to_answer_gives_no_claims_and_is_logged(honest, caplog):
    played, _ = honest
    moment, log, rule = _one_moment(played)
    with caplog.at_level(logging.WARNING, logger=agent.__name__):
        assert explanation.explain(moment, log, Fails()) == rule
    assert any("no answer" in r.message for r in caplog.records)


# --- A2 contributing nothing changes nothing -----------------------------------------------------


class Held(Proposer):
    """`model`, but no answer comes until the test lets it: a model slower than the match."""

    def __init__(self, model: Proposer):
        self.model = model
        self.released = threading.Event()
        self.asked = 0
        self.inline = False  # asked on the thread that makes the cards

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        self.asked += 1
        if threading.current_thread() is threading.main_thread():
            self.inline = True
            raise AssertionError("the card path asked the model")
        if not self.released.wait(timeout=60):
            raise AssertionError("the card path waited for the model")
        return self.model.propose(instructions, prompt)


def _cards(the_pipeline: pipeline.Pipeline) -> list[str]:
    """Seed 1 through `the_pipeline`: every card, as JSON."""
    return [
        c.model_dump_json(exclude={"rendition": {"rendered_at"}})  # wall time, not content
        for item in simulate(1)
        for c in the_pipeline.process(item)
    ]


@pytest.fixture(scope="module")
def alone() -> list[str]:
    return _cards(pipeline.Pipeline())


@pytest.mark.parametrize("model", [Fails, Liar])
def test_no_card_depends_on_a2_or_waits_for_it(model, alone, monkeypatch):
    # D35 and Q32: A. A model that fails, and one whose every number is wrong, both leave every
    # card byte-identical to the run with no model. Q34: A. And none of those cards waits for
    # it: the model gives no answer at all until every card of the match has gone out. Audit is
    # handed its claims, with their verifications, once it does answer.
    audited: list[tuple[Claim, ...]] = []
    verified: list[str] = []
    real = pipeline.audit.record

    def record(moment, claims, verifications, renditions):
        audited.append(tuple(claims))
        verified.extend(v.claim_id for v in verifications)
        real(moment, claims, verifications, renditions)

    monkeypatch.setattr(pipeline.audit, "record", record)
    held = Held(model())
    the_pipeline = pipeline.Pipeline(held)
    try:
        cards = _cards(the_pipeline)
        assert not held.inline
        assert alone
        assert cards == alone
        held.released.set()
        the_pipeline.drain()
    finally:
        held.released.set()
        the_pipeline.close()

    assert held.asked > 1  # every moment was put to the model, one after another
    proposed = [c for claims in audited for c in claims if c.model == MODEL]
    if model is Fails:
        assert not proposed
    else:
        assert proposed
        assert {c.claim_id for c in proposed} <= set(verified)
