"""Applies producer interventions to subsequent cards"""


def mute(lens_id: str, at_clock: int) -> None:
    """Stop cards for `lens_id` from `at_clock` on. Stub: P2 implements it."""
    raise NotImplementedError("the mute circuit breaker lands in P2")


def is_muted(lens_id: str, at_clock: int) -> bool:
    """Whether `lens_id` is muted at `at_clock`. Stub: nothing can be muted yet."""
    return False
