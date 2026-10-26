"""A4: a model wording each lens's spoken claims, and the check that stands in for D22's.

Tests never call a live model. Scripted models stand in: one that echoes what it was given,
which is always traceable, and others that fail in the ways a real one does. The check itself
is tested directly on text, since it is what keeps a live model's words honest.
"""

import json
import threading
from pathlib import Path
from typing import override

import pytest

from apps import pipeline
from matchlens import lenses
from matchlens.config import settings
from matchlens.explanation import Answer, Failure, Proposer
from matchlens.explanation.cache import Cached
from matchlens.models import (
    Claim,
    ClaimType,
    Depth,
    DetailLevel,
    Lens,
    Metric,
    Moment,
    MomentType,
    Operand,
    Ref,
    RefKind,
    SuppressionReason,
    Window,
)
from matchlens.rendering import Written, render, templates, write, writer
from matchlens.selection import Selection
from matchlens.source import MatchSetup, simulate

SIDE = Ref(kind=RefKind.TEAM, id="side-a")
OPPONENT = Ref(kind=RefKind.TEAM, id="side-b")
SCORER = Ref(kind=RefKind.PLAYER, id="p-1")
NAMES = {"side-a": "Larkfield", "side-b": "Ashworth", "p-1": "Tom Brack", "p-2": "Ned Vossel"}
CLOCK = 2_052_000


def _lens(depth: Depth, **changes) -> Lens:
    lens = next(lens for lens in lenses.all_lenses() if lens.depth is depth)
    return lens.model_copy(update=changes)


CASUAL, ANALYST = _lens(Depth.CASUAL), _lens(Depth.ANALYST)
TEAM = _lens(Depth.ENGAGED, focus_team=SIDE.id)


def _moment() -> Moment:
    return Moment(
        moment_id="m", clock_ms=CLOCK, type=MomentType.GOAL, subject=SIDE, importance=0.9,
        trigger_reading_ids=(), trigger_event_ids=("ev",), epoch_id="e", model="spotter",
        model_version="1",
    )  # fmt: skip


def _operand(subject: Ref, metric: Metric, value: float, start_ms: int = CLOCK) -> Operand:
    return Operand(
        subject=subject, metric=metric, window=Window(start_ms=start_ms, end_ms=CLOCK),
        value=value, evidence_ids=(Ref(kind=RefKind.EVENT, id=f"ev-{subject.id}-{metric}"),),
    )  # fmt: skip


def _claim(claim_id: str, *operands: Operand) -> Claim:
    kind = ClaimType.COMPARATIVE if len(operands) == 2 else ClaimType.DESCRIPTIVE
    return Claim(
        claim_id=claim_id, moment_id="m", claim_type=kind, operands=operands,
        backing_reading=None, threshold=None, model="m", model_version="v",
    )  # fmt: skip


SCORED = _claim("c1", _operand(SCORER, Metric.GOALS, 1, start_ms=0))
SCORE = _claim(
    "c2", _operand(OPPONENT, Metric.GOALS, 2, 0), _operand(SIDE, Metric.GOALS, 1, 0)
)  # Ashworth 2, Larkfield 1: the team lens reads it from Larkfield
QUICK = _claim("c3", _operand(SIDE, Metric.BUILD_UP_PASSES, 7, start_ms=CLOCK - 18_000))
DROPPED = _claim("c4", _operand(SIDE, Metric.SHOT_QUALITY, 0.41))


def _selected(*claims: Claim) -> Selection:
    return Selection(claims=claims, suppression_reason=None, importance=0.9)


class Echo(Proposer):
    """A model that gives back the sentences it was shown, joined: always traceable."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, str]] = []
        self._lock = threading.Lock()

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        with self._lock:
            self.asked.append((instructions, prompt))
        text = " — ".join(json.loads(prompt)["sentences"])
        return Answer(json.dumps({"text": text}), "scripted", "s1")


class Says(Proposer):
    def __init__(self, text: str) -> None:
        self.text = text

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        return Answer(self.text, "scripted", "s1")


class Fails(Proposer):
    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        raise TimeoutError("no answer")


# --- what the model is shown -----------------------------------------------------------------


def test_each_lens_is_shown_only_the_sentences_it_would_speak():
    # The analyst speaks the first three claims it kept; the team lens the score and who scored.
    # DROPPED was not selected by either, and no lens is shown it.
    model = Echo()
    write(_moment(), _selected(SCORED, SCORE, QUICK), ANALYST, NAMES, model)
    write(_moment(), _selected(SCORED, SCORE, QUICK), TEAM, NAMES, model)
    (analyst_instructions, analyst), (team_instructions, team) = model.asked
    assert json.loads(analyst) == {
        "depth": "analyst",
        "language": "en",
        # A card is read in seconds, so even the analyst speaks three: how it came about, then
        # the scorer, then the score, which the scoreboard already shows.
        "sentences": [
            "Quick attack: 7 passes in 18 s.",
            "Scorer: Tom Brack, his first of the match.",
            "Ashworth 2, Larkfield 1.",
        ],
    }
    # Told from the focus side and spoken first (D31, Q28: B), then who scored.
    team_sentences = json.loads(team)["sentences"]
    assert team_sentences[0] == "Larkfield trail 1–2."
    assert any("Tom Brack" in sentence for sentence in team_sentences)  # who scored
    assert analyst_instructions != team_instructions
    for prompt in (analyst, team):
        assert "0.41" not in prompt  # DROPPED's value
        assert "importance" not in prompt and "0.9" not in prompt
        assert "moment" not in prompt and "ev" not in prompt  # no moment, no evidence ids


def test_a_lens_that_speaks_no_claim_is_never_asked():
    model = Echo()
    minimal = CASUAL.model_copy(update={"detail_level": DetailLevel.MINIMAL})
    assert write(_moment(), _selected(SCORED, SCORE), minimal, NAMES, model) is None
    silent = Selection(
        claims=(), suppression_reason=SuppressionReason.BELOW_THRESHOLD, importance=0.2
    )
    assert write(_moment(), silent, ANALYST, NAMES, model) is None
    assert model.asked == []


def test_each_depth_has_its_own_register():
    registers = {depth: writer.instructions(depth) for depth in Depth}
    assert len(set(registers.values())) == len(Depth)


# --- what the card says ----------------------------------------------------------------------


def test_the_model_words_follow_the_templates_opening_and_say_who_wrote_them():
    selected = _selected(SCORED, SCORE, QUICK)
    written = write(_moment(), selected, ANALYST, NAMES, Echo())
    assert isinstance(written, Written)
    rendition = render(_moment(), selected, ANALYST, NAMES, written)
    l3 = render(_moment(), selected, ANALYST, NAMES)
    assert rendition.headline == l3.headline
    # The goal left Larkfield behind, so the headline says that and there is no opening line: the
    # model's words are the whole body.
    assert rendition.headline is not None and "deficit" in rendition.headline
    assert l3.body is not None and l3.body.startswith("Quick attack")
    assert rendition.body == written.text
    assert (rendition.model, rendition.model_version) == ("scripted", "s1+writer-7")
    assert (l3.model, l3.model_version) == (templates.MODEL, templates.MODEL_VERSION)
    assert rendition.surviving_claim_ids == l3.surviving_claim_ids


@pytest.mark.parametrize(
    "model",
    [
        Fails(),
        Says("Larkfield scored."),  # not JSON
        Says(json.dumps({"text": "Tom Brack scores his 2nd."})),  # a number it was not given
        Says(json.dumps({"text": ""})),
    ],
    ids=["fails", "not json", "untraceable", "empty"],
)
def test_a_model_that_gives_nothing_keepable_leaves_l3s_words(model):
    selected = _selected(SCORED, SCORE, QUICK)
    # A failure, not a quiet None: the ladder scores it (A5).
    assert isinstance(write(_moment(), selected, ANALYST, NAMES, model), Failure)
    assert render(_moment(), selected, ANALYST, NAMES, None).model == templates.MODEL


# --- the check: every number and name traces to a spoken claim ----------------------------------

GIVEN = [
    "Scorer: Tom Brack, his first of the match.",
    "Larkfield trail 1–2.",
    "A quick attack: 7 passes in 18 s from winning the ball.",
]


def _untraceable(text: str) -> str | None:
    return writer.untraceable(text, GIVEN, NAMES, "en")


@pytest.mark.parametrize(
    "text",
    [
        "Tom Brack's first of the match, after 7 passes in 18 s, still leaves Larkfield 1–2 down.",
        "Brack finishes a quick attack: 7 passes in 18 s. Larkfield trail 1–2.",
        "His first of the match for Tom Brack. Larkfield trail 1–2.",
    ],
)
def test_text_that_says_only_what_it_was_given_traces(text):
    assert _untraceable(text) is None


@pytest.mark.parametrize(
    ("text", "caught"),
    [
        ("Tom Brack scores after 8 passes.", "numbers ['8']"),
        ("Larkfield trail 1–2 after 18.5 s.", "numbers ['18.5']"),
        ("Larkfield trail 1–2 with ten minutes left.", "number words ['ten']"),
        ("Tom Brack's second of the match.", "number words ['second']"),
        ("Their best spell of the half ends with Tom Brack's goal.", "number words ['half']"),
        ("Tom Brack scores; Ashworth still lead.", "names ['Ashworth']"),
        ("Tom Brack, set up by Vossel, scores.", "names ['Vossel']"),
        ("Tom Brack scores in front of the Kop.", "name 'Kop'"),
        (f"Tom Brack scores from a chance worth 0.1 {'x' + 'G'}.", "numbers ['0.1']"),
        (f"Tom Brack beats the {'x' + 'G'} for Larkfield.", "x" + "G"),
        ("We trail 1–2, but Tom Brack has scored.", "a side's voice ['we']"),
        ("Tom Brack scores for our side.", "a side's voice ['our']"),
    ],
)
def test_text_that_adds_a_number_or_a_name_is_caught(text, caught):
    assert _untraceable(text) == caught


# --- in the pipeline -------------------------------------------------------------------------


class Held(Proposer):
    """A model that answers nothing until released: slower than any deadline."""

    def __init__(self) -> None:
        self.released = threading.Event()

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        self.released.wait(timeout=60)
        raise TimeoutError("released")


def _run(writer_model: Proposer | None) -> list:
    cards: list = []
    the_pipeline = pipeline.Pipeline(None, cards.append, writer=writer_model)
    try:
        for item in simulate(1):
            for _ in the_pipeline.process(item):
                pass
        the_pipeline.drain()
    finally:
        the_pipeline.close()
    return cards


def _content(card) -> str:
    return card.model_dump_json(exclude={"rendition": {"rendered_at"}})


@pytest.fixture(scope="module")
def alone() -> list:
    cards: list = []
    the_pipeline = pipeline.Pipeline()
    for item in simulate(1):
        cards.extend(the_pipeline.process(item))
    return cards


def test_only_goals_and_chances_are_worded_by_the_model_and_only_where_claims_are_spoken(alone):
    cards = _run(Echo())
    by_model: dict[str, set[tuple[str, str]]] = {}
    for card in cards:
        key = (card.moment_type.value, card.rendition.lens_id)
        by_model.setdefault(card.rendition.model, set()).add(key)
    worded = by_model["scripted"]
    assert worded
    assert {moment_type for moment_type, _ in worded} <= set(settings.writer_moment_types)
    # The same cards as with no model, in the same order, bar the words and who wrote them;
    # the overlay draws the same words as the card.
    strip = {"rendition": {"rendered_at", "body", "model", "model_version"}, "overlay": True}
    assert [card.model_dump_json(exclude=strip) for card in cards] == [
        card.model_dump_json(exclude=strip) for card in alone
    ]
    assert all(
        card.overlay.payload.get("body", card.rendition.body) == card.rendition.body
        for card in cards
    )


def test_a_writer_past_its_deadline_leaves_every_card_as_l3_wrote_it(alone, monkeypatch):
    monkeypatch.setattr(settings, "writer_deadline_ms", 20)
    held = Held()
    try:
        cards = _run(held)
    finally:
        held.released.set()
    assert [_content(card) for card in cards] == [_content(card) for card in alone]


class Served(Proposer):
    """The demo cache, keeping each writer prompt it answered and what it answered."""

    def __init__(self, cached: Cached) -> None:
        self.cached = cached
        self.served: list[tuple[str, str]] = []

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        answer = self.cached.propose(instructions, prompt)
        self.served.append((prompt, answer.text))
        return answer


def test_every_cached_writer_answer_traces():
    # The demo serves A4's words from the cache (D36, Q38). The runtime check would drop an
    # untraceable one to L3's words anyway; this says so before the demo does.
    # The committed path: conftest blanks the setting so that no other test reads the cache.
    path = Path(type(settings).model_fields["explainer_cache_path"].default)
    if not path.is_file():
        pytest.skip("no demo cache")
    served = Served(Cached.load(str(path), None))
    _run(served)
    if not served.served:
        pytest.skip("the demo cache holds no A4 answers yet")
    for prompt, text in served.served:
        sentences = json.loads(prompt)["sentences"]
        words = json.loads(text)["text"]
        assert writer.untraceable(words, sentences, _names_of_seed_1(), "en") is None, words


def _names_of_seed_1() -> dict[str, str]:
    setup = next(iter(simulate(1)))
    assert isinstance(setup, MatchSetup)  # the stream opens on the setup (D16)
    names = {team.team_id: team.name for team in setup.match.teams}
    return names | {player.player_id: player.name for player in setup.players}
