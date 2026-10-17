"""Entrypoint for the pipeline: the stages in order, over the Match Source stream.

Each stream item goes Ingest → Understanding → Spotting. When Spotting fires a moment, it goes
Explanation → Verification → Selection → Rendering for every lens, and each rendition leaves as a
`Card` through `publish`, which stands in for Service Bus until S5. Audit records the trail.

`run()` drives a whole seeded match as fast as it generates. The delivery app drives the same
`Pipeline` from its paced replay, so a card is published at its moment in match time.
"""

from collections.abc import Callable

from matchlens import audit, explanation, lenses, selection, understanding, verification
from matchlens.ingest import Ingest
from matchlens.models import Claim, Event, Frame, Moment, Verification
from matchlens.rendering import Card, render
from matchlens.source import MatchSetup, StreamItem, simulate
from matchlens.spotting import Spotter

Publish = Callable[[Card], None]


class Pipeline:
    def __init__(self) -> None:
        self._ingest = Ingest()
        self._spotter = Spotter()

    def process(self, item: StreamItem) -> list[Card]:
        """Run one stream item through the stages; the cards it produces, if any."""
        self._ingest.accept(item)
        if isinstance(item, MatchSetup):
            return []
        moment = self._spotter.consider(understanding.observe(item), item)
        if moment is None:
            return []
        return self._editorial(moment, item)

    def _editorial(self, moment: Moment, at: Frame | Event) -> list[Card]:
        record = self._ingest.record()
        # Everything up to and including the moment's clock. A1 replaces this with the frozen-log
        # reader, which also settles whether the clock itself is included (Q6).
        frozen_log = record.events_between(0, moment.clock_ms + 1)

        claims = explanation.explain(moment, frozen_log)
        verifications = [verification.verify(claim, frozen_log) for claim in claims]
        passing = _passing(claims, verifications)

        renditions = []
        cards = []
        for lens in lenses.all_lenses():
            rendition = render(moment, selection.select(moment, passing, lens), lens)
            renditions.append(rendition)
            cards.append(Card(rendition=rendition, display_at_clock=moment.clock_ms))
        audit.record(moment, claims, verifications, renditions)
        return cards


def _passing(claims: list[Claim], verifications: list[Verification]) -> list[Claim]:
    """The claims whose verification passed.

    `Verification` has no verdict until Kehinde's schema lands, so nothing can be shown to have
    passed, and verification fails closed (invariant 5): no claim goes on.
    """
    return []


def run(seed: int, publish: Publish) -> None:
    """Drive one seeded match through the pipeline, publishing every card."""
    pipeline = Pipeline()
    for item in simulate(seed):
        for card in pipeline.process(item):
            publish(card)
