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
from matchlens.audit import Audit
from matchlens.explanation import Answer, Proposer, agent
from matchlens.models import Claim, ClaimType, Metric, Verdict
from matchlens.source import simulate
from matchlens.source.archetypes import DEMO
from tests.explanation.test_builder import Played, _play, _recount

MODEL, VERSION = "fake-model", "fake-1"


def _ref(kind: str, id_: str) -> dict[str, str]:
    return {"kind": kind, "id": id_}


def _reading_operand(r: dict) -> dict:
    return {
        "subject": _ref("team", r["team"]),
        "metric": r["signal"],
        "window": r["window"],
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


# --- on the card path, behind the deadline (D36, Q37) ---------------------------------------------


class Held(Proposer):
    """`model`, but no answer comes until the test lets it: a model slower than the deadline."""

    def __init__(self, model: Proposer):
        self.model = model
        self.released = threading.Event()

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        self.released.wait(timeout=60)
        return self.model.propose(instructions, prompt)


class Counting(Proposer):
    def __init__(self, model: Proposer):
        self.model = model
        self.moments: list[str] = []
        self._lock = threading.Lock()

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        with self._lock:
            self.moments.append(json.loads(prompt)["moment"]["moment_id"])
        return self.model.propose(instructions, prompt)


def _card(c) -> str:
    return c.model_dump_json(exclude={"rendition": {"rendered_at"}})  # wall time, not content


def _run(proposer: Proposer | None, monkeypatch=None) -> tuple[list[str], dict[str, Verdict]]:
    """Seed 1 through the pipeline: every card, as JSON, and every verdict Audit was handed."""
    verdicts: dict[str, Verdict] = {}
    if monkeypatch is not None:
        real = Audit.record

        def record(self, moment, claims, verifications, renditions):
            verdicts.update({v.claim_id: v.verdict for v in verifications})
            real(self, moment, claims, verifications, renditions)

        monkeypatch.setattr(Audit, "record", record)
    cards: list[str] = []
    the_pipeline = pipeline.Pipeline(proposer, lambda c: cards.append(_card(c)))
    try:
        for item in simulate(1):
            cards.extend(_card(c) for c in the_pipeline.process(item))
        the_pipeline.drain()
    finally:
        the_pipeline.close()
    return cards, verdicts


@pytest.fixture(scope="module")
def alone() -> list[str]:
    cards, _ = _run(None)
    assert cards
    return cards


def _moment_types(played: Played) -> dict[str, str]:
    return {x.moment.moment_id: x.moment.type.value for x in played.explained}


def test_a_model_whose_numbers_are_wrong_changes_no_card(alone, monkeypatch):
    # D35's demo shot: A3 rejects every number the liar changed, L7's claims on the same
    # moments pass, and every card ships exactly as it would have with no model at all.
    cards, verdicts = _run(Liar(), monkeypatch)
    proposed = {k: v for k, v in verdicts.items() if ":a" in k}
    assert proposed
    assert set(proposed.values()) == {Verdict.FAIL}
    assert {v for k, v in verdicts.items() if ":c" in k} == {Verdict.PASS}
    assert cards == alone


def test_a_model_that_fails_changes_no_card(alone):
    cards, _ = _run(Fails())
    assert cards == alone


def test_an_honest_models_claims_reach_the_analyst_card_and_nothing_else_moves(
    alone, honest, monkeypatch
):
    cards, verdicts = _run(Honest(), monkeypatch)
    proposed = {k for k, v in verdicts.items() if ":a" in k and v is Verdict.PASS}
    assert proposed
    shown = [json.loads(c) for c in cards]
    spoken = {i for c in shown for i in c["rendition"]["surviving_claim_ids"] if ":a" in i}
    assert spoken and spoken <= proposed
    # Which moments and which cards exist is L7's and Selection's business, not the model's.
    before = [json.loads(c) for c in alone]
    key = [(c["rendition"]["moment_id"], c["rendition"]["lens_id"]) for c in shown]
    assert key == [(c["rendition"]["moment_id"], c["rendition"]["lens_id"]) for c in before]

    # A casual viewer reads exactly what they did: that lens speaks no claim (A2's are among
    # the ones Selection kept for it, as L7's are, and unspoken).
    def seen(cs: list[dict]) -> list[tuple]:
        return [
            (c["rendition"]["headline"], c["rendition"]["body"], c["overlay"])
            for c in cs
            if c["rendition"]["lens_id"] == "match_casual"
        ]

    assert seen(shown) == seen(before)


def test_only_goals_and_chances_are_put_to_the_model_once_each(honest):
    played, _ = honest
    types = _moment_types(_play(1, DEMO))  # the pipeline plays the demo match
    model = Counting(Honest())
    _run(model)
    assert model.moments
    assert len(model.moments) == len(set(model.moments))  # one round trip per moment
    assert {types[m] for m in model.moments} <= {"goal", "chance"}
    assert set(model.moments) == {m for m, t in types.items() if t in ("goal", "chance")}


def test_a_model_slower_than_the_deadline_is_not_waited_for(alone, monkeypatch, caplog):
    monkeypatch.setattr(pipeline.settings, "explainer_deadline_ms", 50)
    held = Held(Honest())
    try:
        with caplog.at_level(logging.WARNING, logger=pipeline.__name__):
            cards, _ = _run(held)
    finally:
        held.released.set()
    assert cards == alone  # every card shipped on L7's claims
    missed = [r for r in caplog.records if "missed its 50 ms deadline" in r.message]
    assert missed  # and every miss is on the record, not silent


def test_each_moments_card_is_made_once_for_every_viewer(honest):
    # D2's identical content (D36, amended): one card per moment and lens, fanned out to every
    # session, never amended, so a viewer further behind cannot be shown a richer one.
    cards, _ = _run(Honest())
    shown = [json.loads(c)["rendition"] for c in cards]
    keys = [(r["moment_id"], r["lens_id"]) for r in shown]
    assert len(keys) == len(set(keys))


# --- the demo cache (D36) ------------------------------------------------------------------------


def test_the_cache_serves_exactly_what_the_live_path_is_asked(alone):
    from matchlens.explanation.cache import Cached, Recording

    recording = Recording(Honest())
    live, _ = _run(recording)
    cached = Cached(recording.answers, live=None)
    served, _ = _run(cached)
    assert served == live  # the same prompts, so the same answers, so the same cards
    assert cached.hits == len(recording.answers) > 0
    # A cache recorded for other prompts answers nothing, and the cards are L7's.
    stale, _ = _run(Cached({}, live=None))
    assert stale == alone


def test_the_prompt_is_a_slice_of_the_log_not_the_whole_of_it(honest):
    played, _ = honest
    x, log = next(
        (x, log)
        for x, log in zip(reversed(played.explained), reversed(played.logs), strict=True)
        if x.moment.type.value in ("goal", "chance")
    )
    prompt = agent.digest(x.moment, log, explanation.by_rule(x.claims))
    shown = [e for e in log.events if f'"{e.event_id}"' in prompt]
    assert len(log.events) > 1000
    assert len(shown) < len(log.events) / 10
    assert f'"{log.events[0].event_id}"' not in prompt
