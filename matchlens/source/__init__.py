"""Produces a deterministic stream of frames and events from a seed"""

from matchlens.source.simulator import simulate
from matchlens.source.stream import MatchSetup, StreamItem

__all__ = ["MatchSetup", "StreamItem", "simulate"]
