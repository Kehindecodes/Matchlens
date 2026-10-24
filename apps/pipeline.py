"""Entrypoint for the pipeline: the stages in order, over the Match Source stream.

Each stream item goes Ingest → Understanding → Spotting. When Spotting fires a moment, it goes
Explanation → Verification → Selection → Rendering for every lens, and each rendition leaves as a
`Card` through `publish`, which stands in for Service Bus until S5. Audit records the trail.

`run()` drives a whole seeded match as fast as it generates. The delivery app drives the same
`Pipeline` from its paced replay, so a card is published at its moment in match time.
"""

from collections.abc import Callable, Iterator, Sequence

from opentelemetry import context, trace

from matchlens import audit, explanation, lenses, selection, verification
from matchlens.ingest import Ingest
from matchlens.models import Claim, Event, Frame, SignalReading, Verdict, Verification
from matchlens.rendering import Card, render
from matchlens.selection import ShownCards
from matchlens.source import MatchSetup, StreamItem, simulate
from matchlens.spotting import Spotter, SpotterResult
from matchlens.understanding import Understanding

Publish = Callable[[Card], None]

tracer = trace.get_tracer(__name__)


class Pipeline:
    def __init__(self) -> None:
        self._ingest = Ingest()
        self._understanding = Understanding(self._ingest.record)
        self._spotter = Spotter(self._ingest.record, self._understanding.epoch_at)
        self._shown = ShownCards()  # Selection's rate-limit state: one pipeline is one match
        self._names: dict[str, str] = {}  # team and player ids to names, from the match setup
        self._readings: list[SignalReading] = []  # derived, append-only: what the explainer reads

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
        record = self._ingest.record()
        # Everything up to and including the moment's clock. A1 replaces this with the frozen-log
        # reader, which also settles whether the clock itself is included (Q6).
        frozen_log = record.events_between(0, result.moment.clock_ms + 1)
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
                claims = explanation.explain(
                    result.moment,
                    frozen_log,
                    self._readings,
                    self._understanding.epochs,
                    record.match,
                )

            # verify() opens its own span, so latency_ms and the span share one stopwatch.
            verifications = [verification.verify(claim, frozen_log) for claim in claims]

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
                renditions.append(rendition)
                if not rendition.suppressed:  # a suppressed rendition is for Audit, not a viewer
                    cards.append(Card(rendition=rendition, display_at_clock=result.moment.clock_ms))
            audit.record(result.moment, claims, verifications, renditions)
            return cards
        finally:
            context.detach(token)


def _passing(claims: list[Claim], verifications: list[Verification]) -> list[Claim]:
    """The claims whose verification passed.

    Fails closed (invariant 5): a claim goes on only if a verification for it says pass.
    """
    passed = {v.claim_id for v in verifications if v.verdict is Verdict.PASS}
    return [c for c in claims if c.claim_id in passed]


def run(seed: int, publish: Publish) -> None:
    """Drive one seeded match through the pipeline, publishing every card."""
    pipeline = Pipeline()
    for item in simulate(seed):
        for card in pipeline.process(item):
            publish(card)
