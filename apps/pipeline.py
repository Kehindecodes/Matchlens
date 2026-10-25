"""Entrypoint for the pipeline: the stages in order, over the Match Source stream.

Each stream item goes Ingest → Understanding → Spotting. When Spotting fires a moment, it goes
Explanation → Verification → Selection → Rendering for every lens, and each rendition leaves as a
`Card` through `publish`, which stands in for Service Bus until S5. Audit records the trail.

With a model (A2), a goal or a chance is also put to it, and its cards wait for the answer until
the moment's enrichment deadline, then go out with L7's claims and whichever of the model's
passed Verification (D36, Q37). Every viewer's card for a moment is that one card, so a viewer
further behind never sees a richer one. A card published later than a viewer's offset would
have released it is released on arrival: release is `max(viewer's due time, deadline)`, and no
card is changed once it has gone. With no model, the cards are L7's alone (D35).

`run()` drives a whole seeded match as fast as it generates. The delivery app drives the same
`Pipeline` from its paced replay, so a card is published at its moment in match time.
"""

import logging
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from opentelemetry import context, trace

from matchlens import audit, explanation, lenses, selection, verification
from matchlens.config import settings
from matchlens.explanation import Proposer, foundry
from matchlens.ingest import FrozenLog, Ingest
from matchlens.models import Claim, SignalReading, Verdict, Verification
from matchlens.rendering import Card, in_full, overlay_packet, render
from matchlens.selection import ShownCards
from matchlens.source import MatchSetup, StreamItem, simulate
from matchlens.spotting import Spotter, SpotterResult
from matchlens.understanding import Understanding

Publish = Callable[[Card], None]

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass(frozen=True)
class _Explained:
    """One moment, explained by rule, with what its editorial stages need."""

    result: SpotterResult
    log: FrozenLog
    claims: list[Claim]  # L7's
    record: verification.Record
    proposed: Future[list[Claim]] | None  # A2's, if this moment was put to the model


class Pipeline:
    def __init__(self, proposer: Proposer | None = None, publish: Publish | None = None) -> None:
        """`proposer` is A2's model. With none, `process` returns each moment's cards.

        With one, a moment's editorial stages run on a thread of their own, one moment at a
        time in the order they fired, because Selection's rate limit counts them in that order.
        Its cards go to `publish`, and `process` returns none.
        """
        if proposer is not None and publish is None:
            raise ValueError("a pipeline with a model publishes its cards when they are ready")
        self._ingest = Ingest()
        self._understanding = Understanding(self._ingest.record)
        self._spotter = Spotter(self._ingest.record, self._understanding.epoch_at)
        self._shown = ShownCards()  # Selection's rate-limit state: one pipeline is one match
        self._names: dict[str, str] = {}  # team and player ids to names, from the match setup
        self._readings: list[SignalReading] = []  # derived, append-only: what the explainer reads
        self._proposer = proposer
        self._publish = publish
        if proposer is not None:
            self._model = ThreadPoolExecutor(settings.explainer_concurrency, "explainer")
            self._editor = ThreadPoolExecutor(1, "editorial")
        self._pending: list[Future[None]] = []  # moments handed to the editor, not yet drained

    def process(self, item: StreamItem) -> Iterator[Card]:
        """Run one stream item through the stages; the cards it produces, if any.

        Ingest, Understanding and Spotting run before this returns. Each moment's editorial
        stages run as the cards are drawn, so a moment's cards are handed on as soon as that
        moment is done, not after every other moment this item fired. With a model, they run
        on the editorial thread instead, and nothing is returned here.
        """
        self._ingest.accept(item)
        if isinstance(item, MatchSetup):
            self._names = {t.team_id: t.name for t in item.match.teams}
            self._names |= {p.player_id: p.name for p in item.players}
            return iter(())
        readings = self._understanding.observe(item)
        self._readings.extend(readings)
        results = self._spotter.consider(readings, item)
        if self._proposer is None:
            return self._cards(results)
        for result in results:
            moment = self._explain(result)
            self._pending.append(self._editor.submit(self._published, moment))
        return iter(())

    def _cards(self, results: Sequence[SpotterResult]) -> Iterator[Card]:
        for result in results:
            yield from self._editorial(self._explain(result))

    def _explain(self, result: SpotterResult) -> _Explained:
        """L7's claims, the record they are checked against, and the model asked if it is due."""
        moment = result.moment
        with _in_trace(result):
            # The wait behind the moments this item fired first, as its own span, so the trace
            # accounts for it rather than leaving a gap (Q27: A).
            tracer.start_span(
                "queued", attributes={"moment_id": moment.moment_id}, start_time=result.fired_ns
            ).end()
            with tracer.start_as_current_span(
                "explanation", attributes={"moment_id": moment.moment_id}
            ):
                reader = self._ingest.record()
                log = FrozenLog(moment, reader, self._readings, self._understanding.epochs)
                claims = explanation.explain(moment, log)
                # What Verification checks against: the record as it stands now, not the log
                # the explainer was frozen to, so a claim citing a later row resolves and fails
                # `temporal` for it.
                record = verification.Record.of(reader, self._readings)
        proposed = None
        if self._proposer is not None and moment.type.value in settings.explainer_moment_types:
            proposed = self._model.submit(explanation.propose, moment, log, claims, self._proposer)
        return _Explained(result, log, claims, record, proposed)

    def _published(self, explained: _Explained) -> None:
        assert self._publish is not None
        for card in self._editorial(explained):
            self._publish(card)

    def _editorial(self, explained: _Explained) -> list[Card]:
        result = explained.result
        moment = result.moment
        with _in_trace(result):
            claims = [*explained.claims, *self._enrichment(explained)]
            # verify() opens its own span, so latency_ms and the span share one stopwatch.
            verifications = [
                verification.verify(claim, moment, claims, explained.record) for claim in claims
            ]
            passing = _passing(claims, verifications)

            renditions = []
            cards = []
            for lens in lenses.all_lenses():
                with tracer.start_as_current_span(
                    "selection", attributes={"moment_id": moment.moment_id, "lens_id": lens.lens_id}
                ):
                    selected = selection.select(moment, passing, lens, self._shown)
                with tracer.start_as_current_span(
                    "rendering", attributes={"moment_id": moment.moment_id}
                ):
                    rendition = render(moment, selected, lens, self._names)
                    body_in_full = in_full(moment, selected, lens, self._names)
                    packet = overlay_packet(moment, selected, lens, self._names, rendition)
                renditions.append(rendition)
                # A suppressed rendition is for Audit, not a viewer, and has no packet.
                if packet is not None:
                    cards.append(
                        Card(
                            rendition=rendition,
                            display_at_clock=moment.clock_ms,
                            moment_type=moment.type,
                            importance=moment.importance,
                            body_in_full=body_in_full,
                            overlay=packet,
                        )
                    )
            audit.record(moment, claims, verifications, renditions)
            return cards

    def _enrichment(self, explained: _Explained) -> list[Claim]:
        """The model's claims for the moment, if it answered by the deadline; otherwise none.

        A miss is logged and put on the trace, never silent. The call is not stopped, only no
        longer waited for: what it says afterwards reaches no card, since a card is not changed
        once it has gone.
        """
        if explained.proposed is None:
            return []
        moment = explained.result.moment
        deadline_s = explained.result.fired_ns / 1e9 + settings.explainer_deadline_ms / 1000
        with tracer.start_as_current_span(
            "explanation.model", attributes={"moment_id": moment.moment_id}
        ) as span:
            try:
                proposed = explained.proposed.result(timeout=max(0.0, deadline_s - time.time()))
            except TimeoutError:
                logger.warning(
                    "explainer: %s missed its %d ms deadline; its cards go on L7's claims",
                    moment.moment_id,
                    settings.explainer_deadline_ms,
                )
                span.set_attribute("deadline_missed", True)
                return []
            span.set_attribute("deadline_missed", False)
            span.set_attribute("claims_proposed", len(proposed))
            return proposed

    def drain(self) -> None:
        """Wait until every moment handed to the editor so far has published its cards."""
        pending, self._pending = self._pending, []
        for future in pending:
            future.result()

    def close(self) -> None:
        """Stop: moments still queued are dropped, and nothing waits for a model call."""
        if self._proposer is not None:
            self._editor.shutdown(wait=False, cancel_futures=True)
            self._model.shutdown(wait=False, cancel_futures=True)


class _in_trace:
    """The moment's trace as the current context, on whichever thread its work is running."""

    def __init__(self, result: SpotterResult):
        self._parent = trace.set_span_in_context(trace.NonRecordingSpan(result.span_context))

    def __enter__(self) -> None:
        self._token = context.attach(self._parent)

    def __exit__(self, *_: object) -> None:
        context.detach(self._token)


def _passing(claims: list[Claim], verifications: list[Verification]) -> list[Claim]:
    """The claims whose verification passed.

    Fails closed (invariant 5): a claim goes on only if a verification for it says pass.
    """
    passed = {v.claim_id for v in verifications if v.verdict is Verdict.PASS}
    return [c for c in claims if c.claim_id in passed]


def run(seed: int, publish: Publish) -> None:
    """Drive one seeded match through the pipeline, publishing every card."""
    pipeline = Pipeline(foundry.from_settings(), publish)
    try:
        for item in simulate(seed):
            for card in pipeline.process(item):
                publish(card)
        pipeline.drain()
    finally:
        pipeline.close()
