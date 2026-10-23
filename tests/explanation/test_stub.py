from matchlens.explanation import explain
from matchlens.models import Moment, MomentType, Ref, RefKind


def _moment(readings: tuple[str, ...], events: tuple[str, ...]) -> Moment:
    return Moment(
        moment_id="m1",
        clock_ms=600_000,
        type=MomentType.TACTICAL_SHIFT,
        subject=Ref(kind=RefKind.TEAM, id="home"),
        importance=0.5,
        trigger_reading_ids=readings,
        trigger_event_ids=events,
        epoch_id="e0",
        model="spotter-rules",
        model_version="spotter-1",
    )


def test_the_stub_claim_cites_the_events_that_fired_the_moment():
    [claim] = explain(_moment((), ("ev-1",)), [])
    assert [(r.kind, r.id) for r in claim.operands[0].evidence_ids] == [(RefKind.EVENT, "ev-1")]


def test_the_stub_claim_cites_the_readings_that_fired_the_moment():
    [claim] = explain(_moment(("rd-1",), ()), [])
    assert [(r.kind, r.id) for r in claim.operands[0].evidence_ids] == [(RefKind.READING, "rd-1")]
