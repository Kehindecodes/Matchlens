"""Decides which measured changes are worth saying something about"""

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from opentelemetry import trace

from matchlens import calltrace
from matchlens.config import settings
from matchlens.ingest import RecordReader
from matchlens.models import (
    Epoch,
    Event,
    Frame,
    Moment,
    MomentType,
    Outcome,
    Ref,
    RefKind,
    Signal,
    SignalReading,
)
from matchlens.spotting.importance import importance, shift_magnitude
from matchlens.understanding.shot_value import is_shot, value

MODEL = "spotter-rules"
MODEL_VERSION = "spotter-1"

tracer = trace.get_tracer(__name__)


@dataclass
class SpotterResult:
    moment: Moment
    span_context: trace.SpanContext


class Spotter:
    """Fires a moment for a goal, a chance, or a signal's `z_match` crossing the threshold.

    No model is involved: the judgement is a threshold on z-scores, gated by confidence and by
    how much of the match the window has seen, so it says nothing in the minutes after a break,
    when the baseline is still mostly the prior (D26). A shift fires when its series crosses the
    threshold, not on every reading that stays above it. Only goals, chances and tactical shifts
    are emitted: `milestone` and `pattern` have no trigger (Q20). Cooldown and duplicate
    suppression are M2's.
    """

    def __init__(self, record: Callable[[], RecordReader], epoch_at: Callable[[int], Epoch]):
        self._record = record
        self._epoch_at = epoch_at
        self._above: dict[tuple[Signal, str], bool] = defaultdict(bool)

    def consider(
        self, readings: Sequence[SignalReading], item: Frame | Event
    ) -> list[SpotterResult]:
        """The moments these readings and this item fire, the readings' first."""
        calltrace.entered("Spotting")
        moments = [moment for reading in readings if (moment := self._shift(reading)) is not None]
        if isinstance(item, Event) and (m := self._event(item)) is not None:
            moments.append(m)
        return [self._result(m) for m in moments]

    def _shift(self, reading: SignalReading) -> Moment | None:
        if not self._crosses(reading):
            return None

        return Moment(
            moment_id=f"moment-{reading.reading_id}",
            clock_ms=reading.clock_ms,
            type=MomentType.TACTICAL_SHIFT,
            subject=Ref(kind=RefKind.TEAM, id=reading.team),
            importance=importance(
                MomentType.TACTICAL_SHIFT, shift_magnitude(reading), reading.confidence
            ),
            trigger_reading_ids=(reading.reading_id,),
            trigger_event_ids=(),
            epoch_id=reading.epoch_id,
            model=MODEL,
            model_version=MODEL_VERSION,
        )

    def _crosses(self, reading: SignalReading) -> bool:
        """Whether the reading is over the threshold when the one before it was not."""
        over = (
            abs(reading.z_match) >= settings.spotter_z_threshold
            and reading.confidence >= settings.spotter_confidence_floor
            and reading.window_ms >= settings.spotter_min_window_ms
        )
        series = (reading.signal, reading.team)
        crossed = over and not self._above[series]
        self._above[series] = over
        return crossed

    def _event(self, event: Event) -> Moment | None:
        if event.team is None:
            return None
        if event.outcome is Outcome.GOAL:
            type_, magnitude = MomentType.GOAL, 1.0
        elif is_shot(event):
            quality = value(event, self._record().match).value
            if quality < settings.spotter_chance_quality:
                return None
            type_, magnitude = MomentType.CHANCE, quality
        else:
            return None

        return Moment(
            moment_id=f"moment-{event.event_id}",
            clock_ms=event.clock_ms,
            type=type_,
            subject=Ref(kind=RefKind.TEAM, id=event.team),
            importance=importance(type_, magnitude),
            trigger_reading_ids=(),
            trigger_event_ids=(event.event_id,),
            epoch_id=self._epoch_at(event.clock_ms).epoch_id,
            model=MODEL,
            model_version=MODEL_VERSION,
        )

    @staticmethod
    def _result(moment: Moment) -> SpotterResult:
        with tracer.start_as_current_span("spotting") as span:
            span.set_attribute("moment_id", moment.moment_id)
            return SpotterResult(moment, span.get_span_context())
