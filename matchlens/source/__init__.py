"""Produces a deterministic stream of frames and events from a seed"""

from matchlens.source.simulator import GENERATOR_VERSION, simulate
from matchlens.source.stream import MatchSetup, StreamItem

__all__ = ["GENERATOR_VERSION", "MatchSetup", "StreamItem", "simulate"]
