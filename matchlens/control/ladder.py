"""A5: the degradation ladder, the one place that knows which rung the match is on (Q41).

Each model has a breaker of its own under one rule: one failed moment takes it down, two good
moments in a row bring it back (Q41: 3A). A model that is down is still asked on every goal and
chance, but its answer is only scored, never waited for or put on a card, so climbing back
costs no extra call and one good answer between two bad ones cannot flip it.

The rung is the prose rung (D35, Q41: 2A): L0 while A4's writer is up, L1 when it is down or
there is none. A2's breaker is shown beside it as "extra claims on or off" and moves no rung,
because a quiet A2 means fewer claims, not different words. No model failure goes below L1:
L7's claims and L3's words need no model. Below L1 is Rendering itself failing on a moment,
and its renditions are then suppressed as `degraded` (Q41: 1A).

The switch is the demo's kill (Q41: 4A): off, every model call raises as if the model were
unreachable, the demo cache included, and the breakers see an ordinary failure.
"""

import logging
import threading
from enum import StrEnum
from typing import override

from pydantic import BaseModel

from matchlens.explanation import Answer, Proposer

logger = logging.getLogger(__name__)

CLIMB_AFTER = 2  # Q41: 3A, good moments in a row that bring a model back up


class Rung(StrEnum):
    L0 = "L0"  # A4's words over L7's claims, plus A2's while it is up
    L1 = "L1"  # L3's template words over L7's claims, no model
    L2 = "L2"  # Rendering failed: the moment's renditions are suppressed, `degraded`


class ModelState(BaseModel):
    configured: bool
    up: bool
    reason: str | None  # why it went down, while it is down


class LadderStatus(BaseModel):
    rung: Rung
    words: ModelState  # A4
    claims: ModelState  # A2
    models_on: bool


class Breaker:
    """One model's up or down, by Q41's rule. Scored on the editorial thread, in moment order."""

    def __init__(self, name: str, changed: "Ladder") -> None:
        self._name = name
        self._ladder = changed
        self.configured = False
        self._down_because: str | None = None
        self._good = 0  # good moments in a row since it went down

    @property
    def up(self) -> bool:
        return self.configured and self._down_because is None

    def failed(self, reason: str) -> None:
        self._good = 0
        if self._down_because is None:
            logger.warning("ladder: %s down: %s", self._name, reason)
            self._down_because = reason
            self._ladder.changed()

    def answered(self) -> None:
        if self._down_because is None:
            return
        self._good += 1
        if self._good >= CLIMB_AFTER:
            logger.warning("ladder: %s back up after %d good answers", self._name, self._good)
            self._down_because = None
            self._good = 0
            self._ladder.changed()

    def state(self) -> ModelState:
        return ModelState(configured=self.configured, up=self.up, reason=self._down_because)


class Ladder:
    def __init__(self) -> None:
        self.writer = Breaker("writer", self)  # A4
        self.explainer = Breaker("explainer", self)  # A2
        self._unrendered = False  # whether the latest moment failed to render
        self._models_on = True
        self._lock = threading.Lock()
        self._version = 0  # counts changes, so a stream sends the status only when it moved

    def configure(self, *, explainer: bool, writer: bool) -> None:
        self.explainer.configured = explainer
        self.writer.configured = writer
        self.changed()

    @property
    def rung(self) -> Rung:
        return self.rung_for(self._unrendered)

    def rung_for(self, unrendered: bool) -> Rung:
        """The rung, given whether the moment being rendered has failed to render."""
        if unrendered:
            return Rung.L2
        return Rung.L0 if self.writer.up else Rung.L1

    @property
    def version(self) -> int:
        return self._version

    @property
    def models_on(self) -> bool:
        return self._models_on

    def switch(self, on: bool) -> None:
        if on != self._models_on:
            logger.warning("ladder: models switched %s", "on" if on else "off")
            self._models_on = on
            self.changed()

    def rendered(self, failed: bool) -> None:
        """Whether the latest moment's renditions could be rendered. No hysteresis: Rendering
        runs on every moment, so the next one is its own probe."""
        if failed != self._unrendered:
            self._unrendered = failed
            self.changed()

    def changed(self) -> None:
        with self._lock:
            self._version += 1

    def status(self) -> LadderStatus:
        return LadderStatus(
            rung=self.rung,
            words=self.writer.state(),
            claims=self.explainer.state(),
            models_on=self._models_on,
        )

    def guard(self, model: Proposer | None) -> Proposer | None:
        """`model` behind the switch, or None for no model."""
        return None if model is None else _Switched(model, self)


class _Switched(Proposer):
    def __init__(self, model: Proposer, ladder: Ladder) -> None:
        self._model = model
        self._ladder = ladder

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        if not self._ladder.models_on:
            raise ConnectionError("models switched off")
        return self._model.propose(instructions, prompt)
