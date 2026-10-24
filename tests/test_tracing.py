"""S6: one trace per moment, spotter → explainer → verifier → selection → rendering.

The tests install an in-memory exporter on the global tracer provider, run seed 1 through
`apps.pipeline.run`, and read back the finished spans. What the tests assume of the code:

- Spans are created through the global provider (`trace.get_tracer(...)`), so the tests can
  capture them without App Insights.
- A span's stage is the first dotted segment of its name: `verification`, or
  `verification.check_claim`, both belong to Verification.
- Every span in a moment's trace carries a `moment_id` attribute.
- A verification span for one claim carries a `claim_id` attribute.

Criterion 5, the Service Bus hop, has no test here: in v1 there is no hop (D23). See Q9.
"""

import gc
import time

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from apps import pipeline
from matchlens.models import Verification
from matchlens.rendering import Card

STAGES = ["spotting", "explanation", "verification", "selection", "rendering"]

_exporter = InMemorySpanExporter()


def _install_provider() -> None:
    """The global provider can be set once per process, so set it once and reuse the exporter."""
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(SimpleSpanProcessor(_exporter))


@pytest.fixture(scope="module")
def traced(monkeypatch_module):
    """Seed 1 end to end: its spans, its cards with the wall time each was published, and the
    verifications handed to Audit."""
    _install_provider()
    _exporter.clear()

    verifications: list[Verification] = []
    real_record = pipeline.audit.record

    def record(moment, claims, verdicts, renditions):
        verifications.extend(verdicts)
        real_record(moment, claims, verdicts, renditions)

    monkeypatch_module.setattr(pipeline.audit, "record", record)

    published: list[tuple[Card, int]] = []
    # A full collection sweeps every match the session has cached, which is not pipeline work,
    # and lands in whichever gap between spans is open when it fires. Freezing the heap first
    # keeps it out of the timings.
    gc.collect()
    gc.freeze()
    try:
        pipeline.run(1, lambda card: published.append((card, time.time_ns())))
    finally:
        gc.unfreeze()
    return list(_exporter.get_finished_spans()), published, verifications


@pytest.fixture(scope="module")
def monkeypatch_module():
    with pytest.MonkeyPatch.context() as mp:
        yield mp


def _moment_ids(published: list[tuple[Card, int]]) -> set[str]:
    return {card.rendition.moment_id for card, _ in published}


def _stage(span: ReadableSpan) -> str:
    return span.name.split(".")[0]


# A finished span always has these; the SDK types them as optional, so narrow them once here.


def _attr(span: ReadableSpan, key: str) -> object:
    return (span.attributes or {}).get(key)


def _trace_id(span: ReadableSpan) -> int:
    assert span.context is not None, span.name
    return span.context.trace_id


def _span_id(span: ReadableSpan) -> int:
    assert span.context is not None, span.name
    return span.context.span_id


def _start(span: ReadableSpan) -> int:
    assert span.start_time is not None, f"{span.name} never started"
    return span.start_time


def _end(span: ReadableSpan) -> int:
    assert span.end_time is not None, f"{span.name} never ended"
    return span.end_time


def _for_moment(spans: list[ReadableSpan], moment_id: str) -> list[ReadableSpan]:
    return [s for s in spans if _attr(s, "moment_id") == moment_id]


def _the_trace(spans: list[ReadableSpan], moment_id: str) -> list[ReadableSpan]:
    """Every span sharing the trace of the moment's spans."""
    tagged = _for_moment(spans, moment_id)
    assert tagged, f"no span carries moment_id={moment_id!r}"
    trace_ids = {_trace_id(s) for s in tagged}
    assert len(trace_ids) == 1, f"moment {moment_id} is spread over {len(trace_ids)} traces"
    [trace_id] = trace_ids
    return [s for s in spans if _trace_id(s) == trace_id]


def _outermost(spans: list[ReadableSpan]) -> list[ReadableSpan]:
    """The spans whose parent is not of their own stage: a stage's whole work, counted once."""
    by_id = {_span_id(s): s for s in spans}
    return [
        s
        for s in spans
        if s.parent is None
        or s.parent.span_id not in by_id
        or _stage(by_id[s.parent.span_id]) != _stage(s)
    ]


def _verification_spans(spans: list[ReadableSpan], claim_id: str) -> list[ReadableSpan]:
    return [s for s in spans if _stage(s) == "verification" and _attr(s, "claim_id") == claim_id]


def _ms(span: ReadableSpan) -> float:
    return (_end(span) - _start(span)) / 1e6


# 1 · One moment produces one trace with at least four spans in the right order


def test_seed_one_produces_a_moment(traced):
    _, published, _ = traced
    assert _moment_ids(published), "no cards published, so there is no moment to trace"


def test_one_moment_is_one_trace(traced):
    spans, published, _ = traced
    for moment_id in _moment_ids(published):
        _the_trace(spans, moment_id)  # asserts a single trace_id


def test_the_trace_has_at_least_four_spans(traced):
    spans, published, _ = traced
    for moment_id in _moment_ids(published):
        assert len(_the_trace(spans, moment_id)) >= 4


def test_the_trace_spans_all_five_stages(traced):
    spans, published, _ = traced
    for moment_id in _moment_ids(published):
        seen = {_stage(s) for s in _the_trace(spans, moment_id)}
        missing = [stage for stage in STAGES if stage not in seen]
        assert not missing, f"moment {moment_id} has no span for {missing}"


def test_the_trace_starts_at_spotting(traced):
    spans, published, _ = traced
    for moment_id in _moment_ids(published):
        roots = [s for s in _the_trace(spans, moment_id) if s.parent is None]
        assert [_stage(s) for s in roots] == ["spotting"], f"roots: {[s.name for s in roots]}"


def test_the_stages_run_in_pipeline_order(traced):
    spans, published, _ = traced
    for moment_id in _moment_ids(published):
        first_start = {}
        for s in _the_trace(spans, moment_id):
            first_start[_stage(s)] = min(first_start.get(_stage(s), _start(s)), _start(s))
        order = sorted((st for st in first_start if st in STAGES), key=first_start.__getitem__)
        assert order == STAGES


# 2 · Searching App Insights by moment_id finds the trace
# App Insights search reads `customDimensions`, which is where span attributes land. The test
# checks the attribute; finding it in the portal is a deploy-time check.


def test_every_span_in_the_trace_carries_the_moment_id(traced):
    spans, published, _ = traced
    for moment_id in _moment_ids(published):
        unlabelled = [
            s.name for s in _the_trace(spans, moment_id) if _attr(s, "moment_id") != moment_id
        ]
        assert not unlabelled, f"spans without moment_id={moment_id!r}: {unlabelled}"


# 3 · Each span carries a duration, and the sum is close to the end-to-end latency
# End to end: from the root span's start to the moment's last card published. With the stubs
# both are well under a millisecond, so the slack is absolute until real agents land.

SLACK_MS = 5.0
SLACK_SHARE = 0.10


def test_every_span_has_a_duration(traced):
    spans, published, _ = traced
    for moment_id in _moment_ids(published):
        for s in _the_trace(spans, moment_id):
            assert _end(s) >= _start(s), s.name


def test_stage_durations_add_up_to_the_end_to_end_latency(traced):
    spans, published, _ = traced
    for moment_id in _moment_ids(published):
        the_trace = _the_trace(spans, moment_id)
        [root] = [s for s in the_trace if s.parent is None]
        last_card = max(t for card, t in published if card.rendition.moment_id == moment_id)
        end_to_end = (last_card - _start(root)) / 1e6
        summed = sum(_ms(s) for s in _outermost(the_trace))

        assert summed <= end_to_end + 1.0, (
            f"stage spans sum to {summed:.2f} ms, more than the {end_to_end:.2f} ms end to end: "
            "two stages' spans overlap, so some work is counted twice"
        )
        assert end_to_end - summed <= max(SLACK_MS, SLACK_SHARE * end_to_end), (
            f"stage spans cover {summed:.2f} of {end_to_end:.2f} ms: work is happening outside them"
        )


# 4 · Verification.latency_ms matches its span duration


def test_every_verification_has_a_span_naming_its_claim(traced):
    spans, _, verifications = traced
    assert verifications, "no verifications reached Audit"
    for v in verifications:
        matching = _verification_spans(spans, v.claim_id)
        assert len(matching) == 1, f"claim {v.claim_id} has {len(matching)} verification spans"


def test_latency_ms_is_the_span_duration(traced):
    spans, _, verifications = traced
    for v in verifications:
        matching = _verification_spans(spans, v.claim_id)
        assert len(matching) == 1, f"claim {v.claim_id} has {len(matching)} verification spans"
        [span] = matching
        assert abs(v.latency_ms - _ms(span)) < 1.0, (
            f"claim {v.claim_id}: latency_ms={v.latency_ms}, span took {_ms(span):.3f} ms"
        )
