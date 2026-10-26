"""L2 end to end: seed 1 through the pipeline, read at Audit (every rendition) and at publish."""

from collections import Counter

import pytest

from apps import pipeline
from matchlens import lenses
from matchlens.audit import Audit
from matchlens.models import Depth, Rendition, SuppressionReason
from matchlens.rendering import Card


@pytest.fixture(scope="module")
def demo():
    renditions: list[Rendition] = []
    published: list[Card] = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            Audit,
            "record",
            lambda audit, moment, claims, verdicts, rendered: renditions.extend(rendered),
        )
        pipeline.run(1, published.append)
    return renditions, published


def test_every_lens_gets_a_rendition_for_every_moment(demo):
    renditions, _ = demo
    per_moment = Counter(r.moment_id for r in renditions)
    assert set(per_moment.values()) == {len(lenses.all_lenses())}


def test_a_silent_lens_leaves_a_record_with_a_reason_and_no_card(demo):
    renditions, published = demo
    silent = [r for r in renditions if r.suppressed]
    assert silent
    assert all(r.suppression_reason is not None for r in silent)
    shown = [r for r in renditions if not r.suppressed]
    assert [c.rendition for c in published] == shown


def test_the_lenses_diverge_on_the_demo_match(demo):
    renditions, _ = demo
    shown = Counter(r.lens_id for r in renditions if not r.suppressed)
    by_depth = {lens.depth: lens.lens_id for lens in lenses.all_lenses()}
    assert (
        0
        < shown[by_depth[Depth.CASUAL]]
        < shown[by_depth[Depth.ENGAGED]]
        < shown[by_depth[Depth.ANALYST]]
    )


def test_casual_is_silent_because_of_its_threshold_not_a_limit(demo):
    renditions, _ = demo
    casual = next(lens for lens in lenses.all_lenses() if lens.depth is Depth.CASUAL)
    reasons = {
        r.suppression_reason for r in renditions if r.lens_id == casual.lens_id and r.suppressed
    }
    assert reasons == {SuppressionReason.BELOW_THRESHOLD}
