"""The offline cache build waits out a rate limit instead of losing the answer."""

from typing import override

import pytest

from matchlens.explanation.agent import Answer, Proposer
from matchlens.explanation.cache import Retrying, rate_limited

ANSWER = Answer(text='{"text": "ok"}', model="scripted", model_version="s1")


class RateLimitError(Exception):
    pass


def _limited() -> Exception:
    try:
        try:
            raise RateLimitError("Error code: 429 - rate_limit_exceeded")
        except RateLimitError as cause:
            raise RuntimeError("service failed to complete the prompt") from cause
    except RuntimeError as wrapped:
        return wrapped


class Scripted(Proposer):
    def __init__(self, *outcomes: Exception | Answer):
        self.outcomes = list(outcomes)
        self.calls = 0

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_a_rate_limit_is_seen_through_the_exception_it_was_wrapped_in():
    assert rate_limited(_limited())
    assert not rate_limited(ValueError("the answer was not JSON"))


def test_a_rate_limited_call_waits_and_asks_again():
    waits: list[float] = []
    live = Scripted(_limited(), _limited(), ANSWER)
    answer = Retrying(live, first_wait_s=10, max_wait_s=15, sleep=waits.append).propose("i", "p")
    assert answer == ANSWER
    assert live.calls == 3
    assert waits == [10, 15]  # doubles, then holds at the cap


def test_a_failure_that_is_not_a_rate_limit_is_raised_at_once():
    live = Scripted(ValueError("bad request"), ANSWER)
    with pytest.raises(ValueError):
        Retrying(live, sleep=lambda _: None).propose("i", "p")
    assert live.calls == 1


def test_it_gives_up_after_its_attempts():
    live = Scripted(*(_limited() for _ in range(3)))
    with pytest.raises(RuntimeError):
        Retrying(live, attempts=3, sleep=lambda _: None).propose("i", "p")
    assert live.calls == 3
