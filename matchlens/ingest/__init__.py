"""Holds the recent frame window in memory and enforces the frame access boundary"""

from matchlens.ingest.events import EventRepository, InMemoryEventRepository
from matchlens.ingest.frames import FrameAccess
from matchlens.ingest.frozen import FrozenLog
from matchlens.ingest.intake import Ingest, RosterNotLoaded
from matchlens.ingest.record import RecordReader

__all__ = [
    "EventRepository",
    "FrameAccess",
    "FrozenLog",
    "InMemoryEventRepository",
    "Ingest",
    "RecordReader",
    "RosterNotLoaded",
]
