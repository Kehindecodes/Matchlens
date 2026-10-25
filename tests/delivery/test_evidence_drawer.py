"""A6: every card opens to the claims behind it and the rows they cite (V7)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps import pipeline
from matchlens import lenses
from matchlens.delivery.http import WEB_DIR, create_app
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.release import ReleaseQueues
from matchlens.delivery.router import CardRouter
from matchlens.delivery.sessions import SessionStore
from matchlens.models import (
    CheckName,
    Claim,
    Event,
    Metric,
    MomentType,
    Rendition,
    Verdict,
    Verification,
    Window,
)
from matchlens.rendering import Card
from matchlens.rendering.evidence import CitedEvent, CitedReading, OperandEvidence
from matchlens.source import simulate

_SEED = 1
_ALL_RELEASED = 10**9  # past the final whistle


class _Run:
    """Seed 1 through the pipeline to one session per lens, with what Audit was handed."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.claims: dict[str, Claim] = {}
        self.verifications: dict[str, Verification] = {}
        self.renditions: list[Rendition] = []

        def record(moment, claims, verifications, renditions):
            self.claims |= {claim.claim_id: claim for claim in claims}
            self.verifications |= {check.claim_id: check for check in verifications}
            self.renditions.extend(renditions)

        monkeypatch.setattr(pipeline.audit, "record", record)
        self.sessions, self.queues = SessionStore(), ReleaseQueues()
        self.by_lens = {
            lens.lens_id: self.sessions.create(lens.lens_id, focus_team=lens.focus_team)
            for lens in lenses.all_lenses()
        }
        self.pipeline = pipeline.Pipeline()
        router = CardRouter(self.sessions, self.queues)
        for item in simulate(_SEED):
            for card in self.pipeline.process(item):
                router.receive(card)
        self.cards = {
            lens_id: self.queues.release_due(session, _ALL_RELEASED)
            for lens_id, session in self.by_lens.items()
        }
        self.events = {item.event_id: item for item in simulate(_SEED) if isinstance(item, Event)}
        self.readings = {reading.reading_id: reading for reading in self.pipeline._readings}

    def every_card(self) -> list[Card]:
        return [card for cards in self.cards.values() for card in cards]


@pytest.fixture(scope="module")
def run() -> _Run:
    with pytest.MonkeyPatch.context() as monkeypatch:
        return _Run(monkeypatch)


def _cited(card: Card) -> list[CitedEvent | CitedReading]:
    rows = []
    for claim in card.evidence:
        for operand in claim.operands:
            rows.extend(operand.cited)
        if claim.backing is not None:
            rows.append(claim.backing)
    return rows


def test_every_card_opens_to_every_claim_behind_it(run):
    cards = run.every_card()
    assert cards
    for card in cards:
        assert card.evidence, card.rendition.rendition_id
        listed = [claim.claim_id for claim in card.evidence]
        assert listed == list(card.rendition.surviving_claim_ids)


def test_no_claim_in_the_drawer_has_an_empty_evidence_list(run):
    for card in run.every_card():
        for claim in card.evidence:
            assert all(operand.cited for operand in claim.operands), claim.claim_id
    # And the model makes it impossible: the guarantee this test documents.
    with pytest.raises(ValidationError):
        OperandEvidence(
            subject="Oakhurst",
            metric=Metric.GOALS,
            value=1,
            window=Window(start_ms=0, end_ms=1),
            cited=(),
        )


def test_a_cited_event_is_a_real_event_at_its_clock(run):
    events = [row for card in run.every_card() for row in _cited(card) if row.kind == "event"]
    assert events
    for row in events:
        event = run.events[row.event_id]
        assert (row.clock_ms, row.period) == (event.clock_ms, event.period)
        assert row.action == event.action


def test_a_cited_reading_shows_its_signal_value_and_z_match(run):
    readings = [row for card in run.every_card() for row in _cited(card) if row.kind == "reading"]
    assert readings
    for row in readings:
        reading = run.readings[row.reading_id]
        assert (row.signal, row.value, row.baseline, row.z_match) == (
            reading.signal,
            reading.value,
            reading.baseline,
            reading.z_match,
        )


def test_the_drawer_recomputes_nothing(run):
    # Every number is the claim's or the verifier's, exactly; the page only prints them.
    for card in run.every_card():
        for shown in card.evidence:
            claim = run.claims[shown.claim_id]
            verification = run.verifications[shown.claim_id]
            assert [operand.value for operand in shown.operands] == [
                operand.value for operand in claim.operands
            ]
            assert [operand.window for operand in shown.operands] == [
                operand.window for operand in claim.operands
            ]
            assert shown.threshold == claim.threshold
            assert shown.recounted == verification.recomputed_value


def test_every_claim_shows_all_six_checks_and_its_verdict(run):
    for card in run.every_card():
        for shown in card.evidence:
            verification = run.verifications[shown.claim_id]
            assert [check.check for check in shown.checks] == list(CheckName)
            for check in shown.checks:
                result = verification.checks[check.check]
                assert (check.status, check.reason) == (result.status, result.reason)
            assert shown.verdict is Verdict.PASS  # only claims that passed reach a card


def test_each_claim_says_whether_the_card_said_it(run):
    spoken = {claim.spoken for card in run.every_card() for claim in card.evidence}
    assert spoken == {True, False}  # a casual card keeps claims it does not say


def test_a_goal_card_opens_to_its_goal_its_shot_quality_and_its_build_up(run):
    # The submission's screenshot: the claim being audited rather than repeated.
    goals = [card for card in run.every_card() if card.moment_type is MomentType.GOAL]
    assert goals
    for card in goals:
        metrics = {operand.metric for claim in card.evidence for operand in claim.operands}
        assert Metric.GOALS in metrics
        actions = {row.action for row in _cited(card) if row.kind == "event"}
        assert "shot" in actions
    assert any(
        {Metric.SHOT_QUALITY, Metric.BUILD_UP_PASSES}
        <= {operand.metric for claim in card.evidence for operand in claim.operands}
        for card in goals
    )


def test_the_drawer_shows_nothing_that_is_not_evidence(run):
    dumped = str([claim.model_dump() for card in run.every_card() for claim in card.evidence])
    for lens in lenses.all_lenses():
        assert lens.lens_id not in dumped
    for field in ("importance", "suppression_reason", "selection"):
        assert field not in dumped


# --- delivery: only released cards, and never on the stream ---------------------------------------


@pytest.fixture(scope="module")
def client(run) -> Iterator[TestClient]:
    app = create_app(MatchStateHub(), run.sessions, run.queues)
    with TestClient(app) as test_client:
        yield test_client


def test_a_released_card_opens_to_its_evidence(run, client):
    lens_id, session = next(iter(run.by_lens.items()))
    card = run.cards[lens_id][0]
    response = client.get(f"/session/{session.session_id}/evidence/{card.rendition.rendition_id}")
    assert response.status_code == 200
    assert response.json() == [claim.model_dump(mode="json") for claim in card.evidence]


def test_a_silent_lens_has_no_drawer_to_open(run, client):
    # A suppressed rendition is a record, never a card: there is nothing to open, so the drawer
    # cannot imply the lens showed something.
    suppressed = [rendition for rendition in run.renditions if rendition.suppressed]
    assert suppressed
    for rendition in suppressed:
        session = run.by_lens[rendition.lens_id]
        response = client.get(f"/session/{session.session_id}/evidence/{rendition.rendition_id}")
        assert response.status_code == 404


def test_another_sessions_card_does_not_open(run, client):
    sessions = list(run.by_lens.values())
    card = run.cards[sessions[0].lens_id][0]
    response = client.get(
        f"/session/{sessions[1].session_id}/evidence/{card.rendition.rendition_id}"
    )
    assert response.status_code == 404


def test_only_the_demo_page_opens_the_drawer():
    # Q42: 1A. The viewer's page never asks for evidence.
    web = Path(WEB_DIR)
    assert "drawer: true" in (web / "app.js").read_text()
    for page in ("watch.js", "delay.js"):
        assert "drawer: true" not in (web / page).read_text()
