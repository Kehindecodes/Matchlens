"""Group E: reference data, computed once offline rather than per match."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from matchlens.models.enums import Signal


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SignalPrior(_Record):
    """What one signal reads across a sample of generated matches: the cold-start reference.

    Only valid for the generator that made it (`generator_version`). `z_prior` against it means
    "unusual for this generator's matches", never "unusual for football".
    """

    signal: Signal
    mean: float
    stddev: Annotated[float, Field(gt=0)]  # a constant signal measures nothing, and z divides by it
    sample_size: Annotated[int, Field(ge=1)]  # measurements, not matches
    generator_version: str
