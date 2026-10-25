"""Entrypoint for the pipeline: the stages in order, over the Match Source stream.

Each stream item goes Ingest → Understanding → Spotting. When Spotting fires a moment, it goes
Explanation → Verification → Selection → Rendering for every lens, and each rendition leaves as a
`Card` through `publish`, which stands in for Service Bus until S5. Audit records the trail.

A model's claims (A2) are off that path (Q34: A). A moment's cards go out with L7's claims, and
the model is asked afterwards, on a thread of its own; what it adds is verified and audited when
it answers, and reaches no card (Q32: A).

`run()` drives a whole seeded match as fast as it generates. The delivery app drives the same
`Pipeline` from its paced replay, so a card is published at its moment in match time.
"""

from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor

from opentelemetry import context, trace

from matchlens import audit, explanation, lenses, selection, verification
from matchlens.explanation import Proposer, foundry
from matchlens.ingest import FrozenLog, Ingest
from matchlens.models import Claim, Event, Frame, SignalReading, Verdict, Verification
from matchlens.rendering import Card, in_full, overlay_packet, render
from matchlens.selection import ShownCards
from matchlens.source import MatchSetup, StreamItem, simulate
from matchlens.spotting import Spotter, SpotterResult
from matchlens.understanding import Understanding

Publish = Callable[[Card], None]

tracer = trace.get_tracer(__name__)


class Pipeline:
    def __init__(self, proposer: Proposer | None = None) -> None:
        """`proposer` is A2's model; with none, the claims are L7's alone (D35)."""
        self._ingest = Ingest()
        self._understanding = Understanding(self._ingest.record)
        self._spotter = Spotter(self._ingest.record, self._understanding.epoch_at)
        self._shown = ShownCards()  # Selection's rate-limit state: one pipeline is one match
        self._names: dict[str, str] = {}  # team and player ids to names, from the match setup
        self._readings: list[SignalReading] = []  # derived, append-only: what the explainer reads
        self._proposer = proposer
        # One thread, so moments are put to the model in the order they fired.
        self._model = ThreadPoolExecutor(1, "explainer") if proposer is not None else None
        self._asked: list[Future[None]] = []  # moments handed to the model, not yet drained

    def process(self, item: StreamItem) -> Iterator[Card]:
        """Run one stream item through the stages; the cards it produces, if any.

        Ingest, Understanding and Spotting run before this returns. Each moment's editorial
        stages run as the cards are drawn, so a moment's cards are handed on as soon as that
        moment is done, not after every other moment this item fired.
        """
        self._ingest.accept(item)
        if isinstance(item, MatchSetup):
            self._names = {t.team_id: t.name for t in item.match.teams}
            self._names |= {p.player_id: p.name for p in item.players}
            return iter(())
        readings = self._understanding.observe(item)
        self._readings.extend(readings)
        results = self._spotter.consider(readings, item)
        return self._cards(results, item)

    def _cards(self, results: Sequence[SpotterResult], at: Frame | Event) -> Iterator[Card]:
        for result in results:
            yield from self._editorial(result, at)

    def _editorial(self, result: SpotterResult, at: Frame | Event) -> list[Card]:
        parent = trace.set_span_in_context(trace.NonRecordingSpan(result.span_context))
        token = context.attach(parent)
        try:
            # The wait behind the moments this item fired first, as its own span, so the trace
            # accounts for it rather than leaving a gap (Q27: A).
            queued = tracer.start_span(
                "queued",
                attributes={"moment_id": result.moment.moment_id},
                start_time=result.fired_ns,
            )
            queued.end()
            with tracer.start_as_current_span(
                "explanation", attributes={"moment_id": result.moment.moment_id}
            ):
                reader = self._ingest.record()
                log = FrozenLog(result.moment, reader, self._readings, self._understanding.epochs)
                claims = explanation.explain(result.moment, log)
                # What Verification checks against: the record as it stands now, not the log
                # the explainer was frozen to, so a claim citing a later row resolves and fails
                # `temporal` for it.
                record = verification.Record.of(reader, self._readings)

            # verify() opens its own span, so latency_ms and the span share one stopwatch.
            verifications = [
                verification.verify(claim, result.moment, claims, record) for claim in claims
            ]

            passing = _passing(claims, verifications)

            renditions = []
            cards = []
            for lens in lenses.all_lenses():
                with tracer.start_as_current_span(
                    "selection",
                    attributes={"moment_id": result.moment.moment_id, "lens_id": lens.lens_id},
                ):
                    selected = selection.select(result.moment, passing, lens, self._shown)
                with tracer.start_as_current_span(
                    "rendering", attributes={"moment_id": result.moment.moment_id}
                ):
                    rendition = render(result.moment, selected, lens, self._names)
                    body_in_full = in_full(result.moment, selected, lens, self._names)
                    packet = overlay_packet(result.moment, selected, lens, self._names, rendition)
                renditions.append(rendition)
                # A suppressed rendition is for Audit, not a viewer, and has no packet.
                if packet is not None:
                    cards.append(
                        Card(
                            rendition=rendition,
                            display_at_clock=result.moment.clock_ms,
                            moment_type=result.moment.type,
                            importance=result.moment.importance,
                            body_in_full=body_in_full,
                            overlay=packet,
                        )
                    )
            audit.record(result.moment, claims, verifications, renditions)
            if self._model is not None:
                self._asked.append(self._model.submit(self._propose, result, log, claims, record))
            return cards
        finally:
            context.detach(token)

    def _propose(
        self, result: SpotterResult, log: FrozenLog, made: list[Claim], record: verification.Record
    ) -> None:
        """A2 for one moment, after its cards have gone: the model's claims, verified and audited.

        `log` is the moment's frozen log, which no later append can reach, so asking late reads
        exactly what asking at once would have.
        """
        assert self._proposer is not None
        parent = trace.set_span_in_context(trace.NonRecordingSpan(result.span_context))
        token = context.attach(parent)
        try:
            with tracer.start_as_current_span(
                "explanation.model", attributes={"moment_id": result.moment.moment_id}
            ):
                claims = explanation.propose(result.moment, log, made, self._proposer)
            if claims:
                # Coverage is over every claim of the moment, L7's included (D22).
                every = [*made, *claims]
                verifications = [
                    verification.verify(claim, result.moment, every, record) for claim in claims
                ]
                audit.record(result.moment, claims, verifications, ())
        finally:
            context.detach(token)

    def drain(self) -> None:
        """Wait until every moment handed to the model so far has been verified and audited."""
        asked, self._asked = self._asked, []
        for future in asked:
            future.result()

    def close(self) -> None:
        """Stop asking the model: what is still queued is dropped, and nothing waits for it."""
        if self._model is not None:
            self._model.shutdown(wait=False, cancel_futures=True)


def _passing(claims: list[Claim], verifications: list[Verification]) -> list[Claim]:
    """The claims whose verification passed.

    Fails closed (invariant 5): a claim goes on only if a verification for it says pass.
    """
    passed = {v.claim_id for v in verifications if v.verdict is Verdict.PASS}
    return [c for c in claims if c.claim_id in passed]


def run(seed: int, publish: Publish) -> None:
    """Drive one seeded match through the pipeline, publishing every card."""
    pipeline = Pipeline(foundry.from_settings())
    for item in simulate(seed):
        for card in pipeline.process(item):
            publish(card)
    pipeline.drain()
