"""A5: the degradation ladder (Q41). Falling back is not failing: every card still arrives."""

import itertools
import json
import logging
import threading
from typing import override

import pytest
from fastapi.testclient import TestClient

from apps import pipeline
from matchlens.audit import Audit
from matchlens.config import settings
from matchlens.control import ladder as ladder_module
from matchlens.control.ladder import Ladder, Rung
from matchlens.delivery.http import create_app
from matchlens.delivery.hub import MatchStateHub
from matchlens.delivery.sessions import SessionStore
from matchlens.explanation import Answer, Proposer
from matchlens.models import Rendition, SuppressionReason
from matchlens.rendering import Card, templates
from matchlens.source import simulate
from tests.explanation.test_agent import Honest, Liar
from tests.rendering.test_writer import Echo, Held, Says

# --- the rule, on its own --------------------------------------------------------------------


def _ladder() -> Ladder:
    ladder = Ladder()
    ladder.configure(explainer=True, writer=True)
    return ladder


def test_one_failure_drops_a_rung_and_two_good_answers_in_a_row_climb_it_back():
    ladder = _ladder()
    assert ladder.rung is Rung.L0
    ladder.writer.failed("missed its deadline")
    assert ladder.rung is Rung.L1  # one rung, never further for a model
    ladder.writer.answered()
    assert ladder.rung is Rung.L1
    ladder.writer.answered()
    assert ladder.rung is Rung.L0


def test_a_model_failing_on_alternate_moments_stays_down_rather_than_flapping():
    ladder = _ladder()
    rungs = []
    for moment in range(10):
        if moment % 2:
            ladder.writer.answered()
        else:
            ladder.writer.failed("an answer that does not parse")
        rungs.append(ladder.rung)
    assert rungs == [Rung.L1] * 10


def test_no_model_failure_goes_below_l1_and_a_rendering_failure_does_for_its_moment_only():
    ladder = _ladder()
    ladder.writer.failed("no answer")
    ladder.explainer.failed("no answer")
    assert ladder.rung is Rung.L1
    ladder.rendered(failed=True)
    assert ladder.rung is Rung.L2
    ladder.rendered(failed=False)
    assert ladder.rung is Rung.L1


def test_with_no_model_configured_the_rung_is_l1():
    assert Ladder().rung is Rung.L1


def test_the_extra_claims_are_shown_beside_the_rung_and_never_move_it():
    ladder = _ladder()
    ladder.explainer.failed("A3 rejected 3 of its 4 claims")
    status = ladder.status()
    assert status.rung is Rung.L0
    assert not status.claims.up and status.claims.reason == "A3 rejected 3 of its 4 claims"


# --- in the pipeline ---------------------------------------------------------------------------


# The first 50 minutes of seed 1: enough goals and chances for every rule here, at half the
# cost of a whole match, which keeps the suite under its two minutes.
_UNTIL_MS = 50 * 60_000


def _items():
    return itertools.takewhile(lambda item: getattr(item, "clock_ms", 0) < _UNTIL_MS, simulate(1))


def _content(card: Card) -> str:
    return card.model_dump_json(exclude={"rendition": {"rendered_at"}})


@pytest.fixture(scope="module")
def alone() -> list[Card]:
    """Seed 1 with no model at all: L7's claims and L3's words."""
    the_pipeline = pipeline.Pipeline()
    return [card for item in _items() for card in the_pipeline.process(item)]


def _run(
    proposer: Proposer | None = None,
    writer: Proposer | None = None,
    ladder: Ladder | None = None,
    between=None,
    **options,
) -> tuple[list[Card], Ladder]:
    """Seed 1 through a pipeline with models; `between(item)` runs after each item is drained,
    so a test can change the ladder at a known point in the match."""
    cards: list[Card] = []
    the_pipeline = pipeline.Pipeline(
        proposer, cards.append, writer=writer, ladder=ladder, **options
    )
    try:
        for item in _items():
            for _ in the_pipeline.process(item):
                pass
            if between is not None:
                the_pipeline.drain()
                between(item)
        the_pipeline.drain()
    finally:
        the_pipeline.close()
    return cards, the_pipeline.ladder


def _worded(cards: list[Card]) -> list[str]:
    """The moments, in order, that have a card the model wrote."""
    return list(
        dict.fromkeys(c.rendition.moment_id for c in cards if c.rendition.model != templates.MODEL)
    )


def test_kill_the_model_and_every_card_still_arrives_on_l7s_claims_and_l3s_words(alone):
    # The criterion the build order exists for. By construction under D35, asserted anyway.
    ladder = Ladder()
    ladder.switch(on=False)
    cards, ladder = _run(Honest(), Echo(), ladder)
    assert [_content(card) for card in cards] == [_content(card) for card in alone]
    assert all(card.rendition.model == templates.MODEL for card in cards)
    claims = {claim for card in cards for claim in card.rendition.surviving_claim_ids}
    assert claims and not any(":a" in claim for claim in claims)  # L7's alone
    status = ladder.status()
    assert status.rung is Rung.L1 and not status.claims.up and not status.models_on


def test_a_model_timeout_drops_exactly_one_rung(alone, monkeypatch):
    monkeypatch.setattr(settings, "writer_deadline_ms", 20)
    held = Held()
    try:
        cards, ladder = _run(Honest(), held)
    finally:
        held.released.set()
    assert ladder.rung is Rung.L1
    assert ladder.status().words.reason == "missed its deadline"
    assert ladder.explainer.up  # the other model is not taken down with it
    assert len(cards) == len(alone)


@pytest.fixture(scope="module")
def nonsense() -> tuple[list[Card], Ladder, list]:
    """A2 lying about every number and A4 answering not-JSON, with the rendering spans kept."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    try:
        cards, ladder = _run(Liar(), Says("Larkfield scored."))
        spans = [s for s in exporter.get_finished_spans() if s.name == "rendering"]
    finally:
        exporter.shutdown()
    return cards, ladder, spans


def test_malformed_output_drops_a_rung_and_the_card_keeps_l3s_words_unrepaired(alone, nonsense):
    cards, ladder, _ = nonsense
    assert ladder.rung is Rung.L1
    assert ladder.status().words.reason == "an answer that does not parse"
    assert [_content(card) for card in cards] == [_content(card) for card in alone]


def test_a2_with_most_of_its_claims_rejected_by_a3_switches_the_extra_claims_off(nonsense):
    _, ladder, _ = nonsense
    assert not ladder.explainer.up
    assert (ladder.status().claims.reason or "").startswith("A3 rejected")


class FailsFirst(Proposer):
    """`model`, except that its first call fails."""

    def __init__(self, model: Proposer) -> None:
        self.model = model
        self.calls = 0
        self._lock = threading.Lock()

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        with self._lock:
            self.calls += 1
            first = self.calls == 1
        if first:
            raise ConnectionError("unreachable")
        return self.model.propose(instructions, prompt)


def test_the_ladder_climbs_back_after_two_good_moments_and_the_cards_between_are_l3s():
    echoed, _ = _run(writer=Echo())
    always = _worded(echoed)
    assert len(always) > 3
    cards, ladder = _run(writer=FailsFirst(Echo()))
    assert ladder.rung is Rung.L0
    # The first moment asked loses only the lens that failed; the next two are asked and
    # scored, not shown; from the fourth on, the model's words are back.
    assert set(_worded(cards)) - {always[0]} == set(always[3:])


def test_a_forced_degradation_mid_match_drops_no_card_and_recovers(alone):
    ladder = Ladder()

    def kill_between_the_halves(item) -> None:
        clock = getattr(item, "clock_ms", 0)
        ladder.switch(on=not 25 * 60_000 <= clock < 31 * 60_000)

    cards, ladder = _run(Honest(), Echo(), ladder, between=kill_between_the_halves)
    keys = [(c.rendition.moment_id, c.rendition.lens_id) for c in cards]
    assert keys == [(c.rendition.moment_id, c.rendition.lens_id) for c in alone]
    by_moment = {c.rendition.moment_id: c.display_at_clock for c in cards}
    worded = [by_moment[moment] for moment in _worded(cards)]
    assert any(clock < 25 * 60_000 for clock in worded)
    assert not any(25 * 60_000 <= clock < 31 * 60_000 for clock in worded)
    assert any(clock >= 31 * 60_000 for clock in worded)  # back up, by the rule
    assert ladder.rung is Rung.L0 and ladder.explainer.up


class HeldOnce(Proposer):
    """`model`, but its first call waits until the test lets it go."""

    def __init__(self, model: Proposer) -> None:
        self.model = model
        self.released = threading.Event()
        self._first = threading.Lock()

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        if self._first.acquire(blocking=False):
            self.released.wait(timeout=60)
        return self.model.propose(instructions, prompt)


def test_a_backlog_of_moments_sheds_the_models(alone, monkeypatch, caplog):
    monkeypatch.setattr(settings, "writer_deadline_ms", 60_000)
    held = HeldOnce(Echo())
    cards: list[Card] = []
    the_pipeline = pipeline.Pipeline(None, cards.append, writer=held, queue_limit=2)
    try:
        with caplog.at_level(logging.WARNING, logger=ladder_module.__name__):
            for item in _items():
                the_pipeline.process(item)
            held.released.set()  # every moment is now queued behind the first one asked
            the_pipeline.drain()
    finally:
        the_pipeline.close()
    downs = [r.message for r in caplog.records if "writer down" in r.message]
    assert downs and "queue pressure" in downs[0]
    assert len(cards) == len(alone)  # shed, not dropped


def test_a_moment_rendering_fails_on_is_suppressed_as_degraded_and_the_next_one_renders(
    alone, monkeypatch
):
    first_goal = next(c.rendition.moment_id for c in alone if c.moment_type.value == "goal")
    real = pipeline.render
    recorded: list[Rendition] = []
    rungs: list[Rung] = []

    def render(moment, *args, **kwargs):
        if moment.moment_id == first_goal:
            raise RuntimeError("a template that does not format")
        return real(moment, *args, **kwargs)

    real_record = Audit.record

    def record(self, moment, claims, verifications, renditions):
        recorded.extend(renditions)
        rungs.append(ladder.rung)
        real_record(self, moment, claims, verifications, renditions)

    monkeypatch.setattr(pipeline, "render", render)
    monkeypatch.setattr(Audit, "record", record)
    ladder = Ladder()
    cards, _ = _run(writer=Echo(), ladder=ladder)

    broken = [r for r in recorded if r.moment_id == first_goal]
    assert broken
    assert all(r.suppressed for r in broken)
    assert {r.suppression_reason for r in broken} <= {
        SuppressionReason.DEGRADED,
        SuppressionReason.OUT_OF_SCOPE,
    }
    assert SuppressionReason.DEGRADED in {r.suppression_reason for r in broken}
    # A rendition produced at L1 or L0 is never `degraded`.
    others = [r for r in recorded if r.moment_id != first_goal]
    assert SuppressionReason.DEGRADED not in {r.suppression_reason for r in others}
    assert Rung.L2 in rungs and rungs[-1] is not Rung.L2
    expected = [c.rendition.rendition_id for c in alone if c.rendition.moment_id != first_goal]
    assert [c.rendition.rendition_id for c in cards] == expected


# --- shown: on the trace, and on the page --------------------------------------------------------


def test_the_rung_is_on_every_rendering_span(nonsense):
    _, _, spans = nonsense
    assert spans
    rungs = [(s.attributes or {}).get("ladder.rung") for s in spans]
    assert set(rungs) == {"L0", "L1"}  # up until the first bad answer, then down
    assert rungs[-1] == "L1"


def test_the_page_reads_the_ladder_and_switches_the_models():
    ladder = _ladder()
    client = TestClient(create_app(MatchStateHub(), SessionStore(), ladder=ladder))
    assert client.get("/ladder").json()["rung"] == "L0"
    switched = client.post("/ladder", json={"models": "off"}).json()
    assert switched["models_on"] is False
    assert not ladder.models_on
    assert client.post("/ladder", json={"models": "maybe"}).status_code == 422
    assert client.post("/ladder", json={"models": "on"}).json()["models_on"] is True


def test_the_switch_makes_a_model_fail_as_if_unreachable():
    ladder = _ladder()
    model = ladder.guard(Echo())
    assert model is not None
    prompt = json.dumps({"sentences": ["Larkfield trail 1–2."]})
    assert model.propose("", prompt).text
    ladder.switch(on=False)
    with pytest.raises(ConnectionError):
        model.propose("", prompt)
