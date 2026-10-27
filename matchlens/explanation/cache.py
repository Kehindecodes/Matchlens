"""Pre-computed model answers for the demo seed, served instead of a live call (D36).

It holds both models' answers, A2's claims and A4's words (Q38), each under its own prompt.

The 25x replay compresses the viewer's offset 25-fold, so no live call fits its deadline. The
demo match is byte-identical from its seed (invariant 9), so its prompts are too, and an answer
recorded offline for a prompt is an answer to exactly that input. Each answer is stored under
the hash of the instructions and the prompt it was given, which is what makes "the cache serves
what the live path would be asked" checkable: a changed digest or prompt version simply misses.

A claim served from here still says which model made it, and still goes through A3.

Build it with `python -m matchlens.explanation.cache <seed>`, which calls the configured model
once per enriched moment, with no deadline, and writes `explainer_cache_path`.
"""

import hashlib
import json
import logging
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import override

from matchlens.explanation.agent import Answer, Proposer

logger = logging.getLogger(__name__)


def key(instructions: str, prompt: str) -> str:
    return hashlib.sha256(f"{instructions}\0{prompt}".encode()).hexdigest()


class Cached(Proposer):
    """Answers from `answers` where the prompt is there, from `live` where it is not."""

    def __init__(self, answers: dict[str, Answer], live: Proposer | None):
        self._answers = answers
        self.live = live
        self.hits = 0

    @classmethod
    def load(cls, path: str, live: Proposer | None) -> "Cached":
        entries = json.loads(Path(path).read_text())
        return cls({key: Answer(**answer) for key, answer in entries.items()}, live)

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        answer = self._answers.get(key(instructions, prompt))
        if answer is not None:
            self.hits += 1
            return answer
        if self.live is None:
            raise LookupError("not in the cache, and no model is configured")
        return self.live.propose(instructions, prompt)


class Recording(Proposer):
    """`live`, keeping every answer under its prompt's key."""

    def __init__(self, live: Proposer):
        self._live = live
        self._lock = threading.Lock()
        self.answers: dict[str, Answer] = {}
        self.seconds: list[float] = []  # how long each call took, for D36's latency target

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        start = time.perf_counter()
        answer = self._live.propose(instructions, prompt)
        with self._lock:
            self.answers[key(instructions, prompt)] = answer
            self.seconds.append(time.perf_counter() - start)
        return answer


def rate_limited(failure: BaseException) -> bool:
    """Whether `failure`, or anything it was raised from, is the service's 429."""
    seen: set[int] = set()
    current: BaseException | None = failure
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = repr(current).lower()
        if "ratelimit" in text or "rate_limit" in text or "error code: 429" in text:
            return True
        current = current.__cause__ or current.__context__
    return False


class Retrying(Proposer):
    """`live`, asked again after a pause when the service says it is out of quota.

    Only for the offline build, where waiting costs nothing: the live path has a deadline and
    a ladder, and must fail fast instead. Only a rate limit is retried; any other failure is
    raised at once. The wait doubles from `first_wait_s` up to `max_wait_s`, and after
    `attempts` calls the last failure is raised, so a deployment with no quota left still stops.
    """

    def __init__(
        self,
        live: Proposer,
        attempts: int = 8,
        first_wait_s: float = 15.0,
        max_wait_s: float = 90.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._live = live
        self._attempts = attempts
        self._first_wait_s = first_wait_s
        self._max_wait_s = max_wait_s
        self._sleep = sleep

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        wait = self._first_wait_s
        for attempt in range(1, self._attempts + 1):
            try:
                return self._live.propose(instructions, prompt)
            except Exception as failure:
                if not rate_limited(failure) or attempt == self._attempts:
                    raise
                logger.warning(
                    "rate limited (attempt %d of %d): waiting %.0f s", attempt, self._attempts, wait
                )
                self._sleep(wait)
                wait = min(wait * 2, self._max_wait_s)
        raise AssertionError("unreachable: the last attempt returns or raises")


def build(seed: int) -> list[Recording]:
    """Every enriched moment of `seed` put to the configured model, waiting as long as it takes.

    One recording for A2's explainer and one for A4's writer, which asks the same model at its
    own reasoning effort.
    """
    from apps.pipeline import Pipeline
    from matchlens.config import settings
    from matchlens.explanation import foundry
    from matchlens.source import simulate

    # Offline, every answer is wanted, however slow: no deadline, a long timeout, one call at a
    # time, and a pause and another try when the deployment's token rate limit is hit.
    settings.explainer_deadline_ms = 10**9
    settings.explainer_timeout_s = 180.0
    settings.explainer_concurrency = 1
    settings.writer_deadline_ms = 10**9
    settings.writer_concurrency = 1
    explainer = foundry.live()
    writer = foundry.live(settings.writer_reasoning_effort)
    if explainer is None or writer is None:
        raise SystemExit("no model configured: set MATCHLENS_FOUNDRY_ENDPOINT and _MODEL_NAME")
    path = Path(settings.explainer_cache_path)

    def recorded(model: Proposer) -> Recording:
        # A rebuild asks again only what is not cached yet: the prompts that are, are answered.
        return Recording(Cached.load(str(path), model) if path.exists() else model)

    explaining, writing = recorded(Retrying(explainer)), recorded(Retrying(writer))
    pipeline = Pipeline(explaining, publish=lambda card: None, writer=writing)
    for item in simulate(seed):
        for _ in pipeline.process(item):
            pass
    pipeline.drain()
    pipeline.close()
    return [explaining, writing]


if __name__ == "__main__":
    from matchlens.config import settings

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    recordings = build(int(sys.argv[1]) if len(sys.argv) > 1 else settings.match_seed)
    answers = {key: answer for recording in recordings for key, answer in recording.answers.items()}
    Path(settings.explainer_cache_path).write_text(
        json.dumps({key: answer._asdict() for key, answer in sorted(answers.items())}, indent=1)
        + "\n"
    )
    took = sorted(seconds for recording in recordings for seconds in recording.seconds)
    print(f"{len(answers)} answers written to {settings.explainer_cache_path}")
    if took:
        print(f"per call: median {took[len(took) // 2]:.1f} s, slowest {took[-1]:.1f} s")
