"""The frame window, and the only way to read it."""

from collections import deque

from matchlens.models import Frame


class FrameWindow:
    """The most recent `retention_ms` of frames, in memory. Older frames are evicted on append."""

    def __init__(self, retention_ms: int):
        if retention_ms <= 0:
            raise ValueError("retention_ms must be positive")
        self.retention_ms = retention_ms
        self._frames: deque[Frame] = deque()

    def __len__(self) -> int:
        return len(self._frames)

    def append(self, frame: Frame) -> None:
        if self._frames and frame.clock_ms < self._frames[-1].clock_ms:
            raise ValueError("frames must arrive in clock order")
        self._frames.append(frame)
        horizon = frame.clock_ms - self.retention_ms
        while self._frames[0].clock_ms <= horizon:
            self._frames.popleft()

    def between(self, clock_ms: int, span_ms: int) -> list[Frame]:
        """Frames in `(clock_ms - span_ms, clock_ms]`.

        A span longer than the retention would silently return a truncated window, so it is
        refused instead.
        """
        if not 0 <= span_ms <= self.retention_ms:
            raise ValueError(f"span_ms must be within 0..{self.retention_ms}, got {span_ms}")
        start = clock_ms - span_ms
        return [f for f in self._frames if start < f.clock_ms <= clock_ms]


class FrameAccess:
    """Understanding's read of the frame window. Agent-facing code is never given one."""

    def __init__(self, window: FrameWindow):
        self._window = window

    def frame_window(self, clock_ms: int, span_ms: int) -> list[Frame]:
        """Frames in `(clock_ms - span_ms, clock_ms]`."""
        return self._window.between(clock_ms, span_ms)
