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


def build(seed: int) -> list[Recording]:
    """Every enriched moment of `seed` put to the configured model, waiting as long as it takes.

    One recording for A2's explainer and one for A4's writer, which asks the same model at its
    own reasoning effort.
    """
    from apps.pipeline import Pipeline
    from matchlens.config import settings
    from matchlens.explanation import foundry
    from matchlens.source import simulate

    # Offline, every answer is wanted, however slow: no deadline, a long timeout, and one call
    # at a time, which stays under the deployment's token rate limit.
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

    explaining, writing = recorded(explainer), recorded(writer)
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
