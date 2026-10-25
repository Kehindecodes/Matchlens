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

With a writer (A4), a goal's or a chance's lenses are also worded by a model, each from its own
selected claims, and the cards wait for those words until a second deadline from when Rendering
starts, then go out with whichever came, and L3's words for the rest (Q38).

Each model has a breaker on the ladder (A5, Q41). A model that missed a deadline, failed,
answered nonsense, had most of its claims rejected by A3, or met a backlog of moments is down
from the next moment on. While down it is still asked, but not waited for and not shown, and
two good answers in a row bring it back. A moment Rendering fails on is suppressed as
`degraded` rather than lost.

Beside the cards, each moment reports what every lens did with it (P1, Q42), suppressed
renditions and the importance and rate-limit count Selection judged included, to `report`. A
moment that fails outside Rendering is logged and reported failed, so no lens is left looking
quiet for a moment nobody can see was lost. None of it reaches a viewer.

`run()` drives a whole seeded match as fast as it generates. The delivery app drives the same
`Pipeline` from its paced replay, so a card is published at its moment in match time.
"""

import logging
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from opentelemetry import context, trace

from matchlens import audit, explanation, lenses, selection, verification
from matchlens.config import settings
from matchlens.control.ladder import Breaker, Ladder, Rung
from matchlens.explanation import Failure, Proposer, foundry
from matchlens.ingest import FrozenLog, Ingest
from matchlens.models import Claim, Lens, Moment, SignalReading, Verdict, Verification
from matchlens.rendering import (
    Card,
    LensOutcome,
    MomentOutcome,
    Written,
    degraded,
    in_full,
    overlay_packet,
    render,
    write,
)
from matchlens.selection import Selection, ShownCards
from matchlens.source import MatchSetup, StreamItem, simulate
from matchlens.spotting import Spotter, SpotterResult
from matchlens.understanding import Understanding

Publish = Callable[[Card], None]
Report = Callable[[MomentOutcome], None]

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass(frozen=True)
class _Explained:
    """One moment, explained by rule, with what its editorial stages need."""

    result: SpotterResult
    log: FrozenLog
    claims: list[Claim]  # L7's
    record: verification.Record
    proposed: "Future[_Timed] | None"  # A2's, if this moment was put to the model


# What a model call gave, and the wall time it finished at: an answer read after its deadline
# may have come in time, and one that came late must not count as good.
_Timed = tuple[Any, float]


def _timed(function: Callable[..., Any], *args: Any) -> _Timed:
    return function(*args), time.time()


@dataclass(frozen=True)
class _Shadow:
    """A model asked while down, or shed: its answer is scored, never shown (Q41: 3A)."""

    breaker: Breaker
    deadline_s: float
    asked: list["Future[_Timed]"]
    explained: _Explained | None  # A2's moment, to verify its claims; None for A4


class Pipeline:
    def __init__(
        self,
        proposer: Proposer | None = None,
        publish: Publish | None = None,
        writer: Proposer | None = None,
        ladder: Ladder | None = None,
        queue_limit: int | None = None,
        report: Report | None = None,
    ) -> None:
        """`proposer` is A2's model and `writer` A4's. With neither, `process` returns each
        moment's cards.

        With either, a moment's editorial stages run on a thread of their own, one moment at a
        time in the order they fired, because Selection's rate limit counts them in that order.
        Its cards go to `publish`, and `process` returns none.

        `ladder` is where the rung is kept (A5), a fresh one if none is given; both models are
        put behind its switch. `queue_limit` is how many moments may wait for the editor before
        the models are shed. None for an unpaced run, which queues every moment at once by
        design; the paced feed passes `settings.ladder_queue_limit`.

        `report` is told, once per moment and in the order they fired, what each lens did with
        it (P1). It is called on whichever thread the moment's editorial stages run on.
        """
        self._waits = proposer is not None or writer is not None
        if self._waits and publish is None:
            raise ValueError("a pipeline with a model publishes its cards when they are ready")
        self._ingest = Ingest()
        self._understanding = Understanding(self._ingest.record)
        self._spotter = Spotter(self._ingest.record, self._understanding.epoch_at)
        self._shown = ShownCards()  # Selection's rate-limit state: one pipeline is one match
        self._names: dict[str, str] = {}  # team and player ids to names, from the match setup
        self._readings: list[SignalReading] = []  # derived, append-only: what the explainer reads
        self.ladder = Ladder() if ladder is None else ladder
        self.ladder.configure(explainer=proposer is not None, writer=writer is not None)
        self._proposer = self.ladder.guard(proposer)
        self._publish = publish
        self._report = report
        self._writer = self.ladder.guard(writer)
        self._queue_limit = queue_limit
        self._shadows: list[_Shadow] = []  # models asked while down, scored at the next moment
        if proposer is not None:
            self._model = ThreadPoolExecutor(settings.explainer_concurrency, "explainer")
        if writer is not None:
            self._writing = ThreadPoolExecutor(settings.writer_concurrency, "writer")
        if self._waits:
            self._editor = ThreadPoolExecutor(1, "editorial")
        self._pending: list[Future[None]] = []  # moments handed to the editor, not yet drained
        self._queued = 0  # moments handed to the editor and not yet published: the backlog
        self._queued_lock = threading.Lock()

    def process(self, item: StreamItem) -> Iterator[Card]:
        """Run one stream item through the stages; the cards it produces, if any.

        Ingest, Understanding and Spotting run before this returns. Each moment's editorial
        stages run as the cards are drawn, so a moment's cards are handed on as soon as that
        moment is done, not after every other moment this item fired. With a model, they run
        on the editorial thread instead, and nothing is returned here.
        """
        self._ingest.accept(item)
        if isinstance(item, MatchSetup):
            self._names = {team.team_id: team.name for team in item.match.teams}
            self._names |= {player.player_id: player.name for player in item.players}
            return iter(())
        readings = self._understanding.observe(item)
        self._readings.extend(readings)
        results = self._spotter.consider(readings, item)
        if not self._waits:
            return self._cards(results)
        for result in results:
            moment = self._explain(result)
            with self._queued_lock:
                self._queued += 1
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
            proposed = self._model.submit(
                _timed, explanation.propose, moment, log, claims, self._proposer
            )
        return _Explained(result, log, claims, record, proposed)

    def _published(self, explained: _Explained) -> None:
        assert self._publish is not None
        try:
            for card in self._guarded(explained):
                self._publish(card)
        finally:
            with self._queued_lock:
                self._queued -= 1

    def _guarded(self, explained: _Explained) -> list[Card]:
        """`_editorial`, with a failure logged and reported before it is raised on.

        On the editorial thread nothing reads the exception until `drain`, which the delivery
        app never calls, so without this a moment that fails outside Rendering would vanish and
        its lenses would look quiet. Rendering's own failures do not come here: they are
        suppressed as `degraded` and the moment completes (A5).
        """
        moment = explained.result.moment
        try:
            return self._editorial(explained)
        except Exception as error:
            logger.exception(
                "editorial: %s failed; no lens has a rendition for it", moment.moment_id
            )
            self._tell(moment, (), failure=f"{type(error).__name__}: {error}")
            raise

    def _editorial(self, explained: _Explained) -> list[Card]:
        result = explained.result
        moment = result.moment
        with _in_trace(result):
            self._score_shadows()
            shed = self._backlog()
            proposed = self._enrichment(explained, shed)
            claims = [*explained.claims, *proposed]
            # verify() opens its own span, so latency_ms and the span share one stopwatch.
            verifications = [
                verification.verify(claim, moment, claims, explained.record) for claim in claims
            ]
            passing = _passing(claims, verifications)
            if explained.proposed is not None and shed is None and self.ladder.explainer.up:
                _score(self.ladder.explainer, [_rejected_most(proposed, verifications)])

            selections = []
            for lens in lenses.all_lenses():
                with tracer.start_as_current_span(
                    "selection", attributes={"moment_id": moment.moment_id, "lens_id": lens.lens_id}
                ):
                    selections.append((lens, selection.select(moment, passing, lens, self._shown)))
            written = self._written(moment, selections, shed)

            renditions = []
            cards = []
            unrendered = False
            for lens, selected in selections:
                with tracer.start_as_current_span(
                    "rendering", attributes={"moment_id": moment.moment_id}
                ) as span:
                    words = written.get(lens.lens_id)
                    try:
                        rendition = render(moment, selected, lens, self._names, words)
                        body_in_full = in_full(moment, selected, lens, self._names)
                        packet = overlay_packet(moment, selected, lens, self._names, rendition)
                        rung = Rung.L1 if words is None else Rung.L0
                    except Exception:
                        # Below L1 (Q41: 1A): no words at all, so the rendition is suppressed
                        # as `degraded`, on the record, and the next moment tries again.
                        logger.exception(
                            "rendering: %s failed on %s; suppressed as degraded",
                            moment.moment_id,
                            lens.lens_id,
                        )
                        rendition, packet, rung = degraded(moment, selected, lens), None, Rung.L2
                        body_in_full = ""
                        unrendered = True
                    span.set_attribute("rendition.rung", rung.value)
                    span.set_attribute("ladder.rung", self.ladder.rung_for(unrendered).value)
                    span.set_attribute("ladder.claims_on", self.ladder.explainer.up)
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
            self.ladder.rendered(unrendered)
            audit.record(moment, claims, verifications, renditions)
            self._tell(
                moment,
                [
                    LensOutcome(
                        lens_id=lens.lens_id,
                        rendition=rendition,
                        importance=selected.importance,
                        shown_in_window=self._shown.in_window(lens.lens_id, moment.clock_ms),
                    )
                    for (lens, selected), rendition in zip(selections, renditions, strict=True)
                ],
            )
            return cards

    def _tell(
        self, moment: Moment, outcomes: Sequence[LensOutcome], failure: str | None = None
    ) -> None:
        """Report what the lenses did with `moment` (P1), if anything is listening."""
        if self._report is None:
            return
        self._report(
            MomentOutcome(
                moment_id=moment.moment_id,
                clock_ms=moment.clock_ms,
                moment_type=moment.type,
                lens_ids=tuple(lens.lens_id for lens in lenses.all_lenses()),
                outcomes=tuple(outcomes),
                failure=failure,
            )
        )

    def _backlog(self) -> str | None:
        """Why the models are shed for this moment, or None: more moments waiting for the
        editor than `queue_limit` (Q41: 3A). Waiting on a model would only make them later."""
        if self._queue_limit is None:
            return None
        with self._queued_lock:
            waiting = self._queued - 1  # less this one
        if waiting <= self._queue_limit:
            return None
        return f"queue pressure: {waiting} moments waiting"

    def _enrichment(self, explained: _Explained, shed: str | None) -> list[Claim]:
        """The model's claims for the moment, if it is up and answered by the deadline;
        otherwise none.

        A miss is logged and put on the trace, never silent, and takes the explainer down. The
        call is not stopped, only no longer waited for: what it says afterwards reaches no card,
        since a card is not changed once it has gone. Asked while down or shed, its answer is
        only scored, at the next moment.
        """
        if explained.proposed is None:
            return []
        moment = explained.result.moment
        breaker = self.ladder.explainer
        deadline_s = explained.result.fired_ns / 1e9 + settings.explainer_deadline_ms / 1000
        if shed is not None or not breaker.up:
            if shed is not None:
                breaker.failed(shed)
            self._shadows.append(_Shadow(breaker, deadline_s, [explained.proposed], explained))
            return []
        with tracer.start_as_current_span(
            "explanation.model", attributes={"moment_id": moment.moment_id}
        ) as span:
            answer = _answer(explained.proposed, deadline_s)
            span.set_attribute("deadline_missed", answer is _MISSED)
            if answer is _MISSED:
                logger.warning(
                    "explainer: %s missed its %d ms deadline; its cards go on L7's claims",
                    moment.moment_id,
                    settings.explainer_deadline_ms,
                )
            if isinstance(answer, Failure):
                breaker.failed(answer.reason)
                return []
            span.set_attribute("claims_proposed", len(answer))
            return answer

    def _written(
        self, moment: Moment, selections: list[tuple[Lens, Selection]], shed: str | None
    ) -> dict[str, Written]:
        """A4's words for each lens of `moment` that it answered by the deadline, by lens id.

        Every lens is asked at once, and all of them share one deadline from now. A lens it
        missed, failed or had nothing to word for is not in the result, and its card keeps L3's
        words. A miss or a failure is logged and put on the trace, and takes the writer down;
        the call goes on unwaited-for. Down, it is asked and only scored; shed, not asked.
        """
        if self._writer is None or moment.type.value not in settings.writer_moment_types:
            return {}
        breaker = self.ladder.writer
        if shed is not None:
            breaker.failed(shed)
            return {}
        deadline_s = time.time() + settings.writer_deadline_ms / 1000
        asked = {
            lens.lens_id: self._writing.submit(
                _timed, write, moment, selected, lens, self._names, self._writer
            )
            for lens, selected in selections
        }
        if not breaker.up:
            self._shadows.append(_Shadow(breaker, deadline_s, list(asked.values()), None))
            return {}
        written: dict[str, Written] = {}
        with tracer.start_as_current_span(
            "rendering.model", attributes={"moment_id": moment.moment_id}
        ) as span:
            missed = []
            reasons: list[str | None] = []
            for lens_id, future in asked.items():
                words = _answer(future, deadline_s)
                if words is _MISSED:
                    missed.append(lens_id)
                if isinstance(words, Failure):
                    reasons.append(words.reason)
                elif isinstance(words, Written):
                    written[lens_id] = words
                    reasons.append(None)
            if missed:
                logger.warning(
                    "writer: %s missed its %d ms deadline on %s; L3's words go out instead",
                    moment.moment_id,
                    settings.writer_deadline_ms,
                    ", ".join(missed),
                )
            _score(breaker, reasons)
            span.set_attribute("deadline_missed", missed)
            span.set_attribute("lenses_written", sorted(written))
        return written

    def _score_shadows(self) -> None:
        """Score the models asked while down, in the order they were asked, each waited for
        until its own deadline at most. Scoring here, before this moment looks at the ladder,
        rather than whenever an answer lands, keeps a seeded run's cards the same every time
        (invariant 9). The price: a moment within a deadline of a down model's last call can
        wait out the rest of that deadline."""
        shadows, self._shadows = self._shadows, []
        for shadow in shadows:
            reasons: list[str | None] = []
            for future in shadow.asked:
                answer = _answer(future, shadow.deadline_s)
                if isinstance(answer, Failure):
                    reasons.append(answer.reason)
                elif shadow.explained is not None:
                    reasons.append(_rejected_most(answer, self._verified(shadow.explained, answer)))
                elif answer is not None:
                    reasons.append(None)  # words it was asked for; None is nothing to word
            _score(shadow.breaker, reasons)

    def _verified(self, explained: _Explained, proposed: list[Claim]) -> list[Verification]:
        moment = explained.result.moment
        claims = [*explained.claims, *proposed]
        return [verification.verify(claim, moment, claims, explained.record) for claim in proposed]

    def drain(self) -> None:
        """Wait until every moment handed to the editor so far has published its cards."""
        pending, self._pending = self._pending, []
        for future in pending:
            future.result()

    def close(self) -> None:
        """Stop: moments still queued are dropped, and nothing waits for a model call."""
        if self._waits:
            self._editor.shutdown(wait=False, cancel_futures=True)
        if self._proposer is not None:
            self._model.shutdown(wait=False, cancel_futures=True)
        if self._writer is not None:
            self._writing.shutdown(wait=False, cancel_futures=True)


class _in_trace:
    """The moment's trace as the current context, on whichever thread its work is running."""

    def __init__(self, result: SpotterResult):
        self._parent = trace.set_span_in_context(trace.NonRecordingSpan(result.span_context))

    def __enter__(self) -> None:
        self._token = context.attach(self._parent)

    def __exit__(self, *_: object) -> None:
        context.detach(self._token)


_MISSED = Failure("missed its deadline")


def _answer(future: "Future[_Timed]", deadline_s: float) -> Any:
    """What the call gave, or `_MISSED` if it gave nothing by `deadline_s`."""
    try:
        answer, finished_s = future.result(timeout=max(0.0, deadline_s - time.time()))
    except TimeoutError:
        return _MISSED
    return answer if finished_s <= deadline_s else _MISSED


def _score(breaker: Breaker, reasons: Sequence[str | None]) -> None:
    """One moment's outcome for `breaker`: down on any failure, an answer if every call it was
    asked answered well, and nothing if it was asked nothing."""
    failures = [reason for reason in reasons if reason is not None]
    if failures:
        breaker.failed(failures[0])
    elif reasons:
        breaker.answered()


def _rejected_most(proposed: Sequence[Claim], verifications: Sequence[Verification]) -> str | None:
    """A failure if A3 rejected more than half the claims A2 proposed (Q41: 3A), else None."""
    ids = {claim.claim_id for claim in proposed}
    rejected = sum(v.claim_id in ids and v.verdict is not Verdict.PASS for v in verifications)
    if rejected * 2 > len(ids):
        return f"A3 rejected {rejected} of its {len(ids)} claims"
    return None


def _passing(claims: list[Claim], verifications: list[Verification]) -> list[Claim]:
    """The claims whose verification passed.

    Fails closed (invariant 5): a claim goes on only if a verification for it says pass.
    """
    passed = {v.claim_id for v in verifications if v.verdict is Verdict.PASS}
    return [c for c in claims if c.claim_id in passed]


def run(seed: int, publish: Publish) -> None:
    """Drive one seeded match through the pipeline, publishing every card."""
    writer = foundry.from_settings(settings.writer_reasoning_effort)
    pipeline = Pipeline(foundry.from_settings(), publish, writer=writer)
    try:
        for item in simulate(seed):
            for card in pipeline.process(item):
                publish(card)
        pipeline.drain()
    finally:
        pipeline.close()
