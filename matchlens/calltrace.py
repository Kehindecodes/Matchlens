"""A simple ordered log of which components a run entered (S4).

Each component's primary callable calls `entered(<its architecture-table name>)`. Outside a
`recording()` block it does nothing, so it costs one context-variable read per call.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_log: ContextVar[list[str] | None] = ContextVar("calltrace", default=None)


def entered(component: str) -> None:
    log = _log.get()
    if log is not None:
        log.append(component)


@contextmanager
def recording() -> Iterator[list[str]]:
    """Collect every `entered` call in this context, in order."""
    log: list[str] = []
    token = _log.set(log)
    try:
        yield log
    finally:
        _log.reset(token)
