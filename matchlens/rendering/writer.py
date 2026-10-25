"""A4: a model rewriting one lens's spoken claims in that lens's register (L0).

The model is shown the sentences L3 would speak for this lens, one per claim, and the lens's
depth and language. Nothing else: not the moment, not its importance, not another lens's claims,
not the claims L3 would leave unspoken. The headline and the opening line stay the template's
(Q38: 1A), so the model only ever words claims.

What it answers is checked before it can reach a card (Q38: 2A), because nothing downstream will
(D22): every number, every number word and every name it writes must already be in the sentences
it was given, it never names shot quality by its abbreviation (invariant 12), and it never
speaks as a side, "we" or "our" (D31). An answer that fails any of these, or does not parse,
or never comes, gives no text, and the card keeps L3's words.

What the check cannot see, stated: an assertion with no number and no name in it ("their best
spell of the half" is caught by "half"; "a dominant display" is not), and a name the roster does
not hold opening a sentence. Both rest on the instructions.
"""

import json
import logging
import re
from collections.abc import Mapping, Sequence
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, ValidationError

from matchlens.explanation import Answer, Proposer
from matchlens.models import Depth, Lens
from matchlens.rendering import templates

logger = logging.getLogger(__name__)

PROMPT_VERSION = "writer-2"  # bump by hand whenever the instructions or the prompt change

# The abbreviation invariant 12 bans, spelt so that no file here contains it: the model has to
# be told the word it may not use, and the check has to look for it.
_BANNED = "x" + "G"


class Written(NamedTuple):
    """Words a model wrote for one rendition, and which model wrote them (invariant 7)."""

    text: str
    model: str
    model_version: str


class _Response(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str


_REGISTERS = {
    Depth.CASUAL: (
        "Casual: a viewer who wants to know what happened, in plain words. Short, warm, no "
        "statistics vocabulary. Never a number, as digits or in words."
    ),
    Depth.ENGAGED: (
        "Engaged: a viewer who follows the game closely. Natural match-commentary prose that "
        "keeps every number it is given, with no jargon beyond the sentences' own."
    ),
    Depth.ANALYST: (
        "Analyst: a viewer who wants the mechanism and the numbers. Precise and compact; lead "
        "with how it happened, keep every number exactly as given, and keep the labels."
    ),
}

INSTRUCTIONS = f"""\
You rewrite a few short sentences about a football match as one short passage for one viewer.
The sentences are verified facts. Your passage must say what they say, all of it, and nothing
more.

Answer with one JSON object and nothing else: {{"text": "<your passage>"}}.

Rules. A passage that breaks one is thrown away and the viewer gets the sentences as they are.
- Use only the facts in the sentences. Add no fact, cause, comparison, history, emphasis or
  judgement of your own: if a sentence does not say it, you do not say it.
- Change no word that decides what a fact means. Keep every "his", "a", "the", "first",
  "again", "so far", "before", "than" and "or more" as given: "his first of the match" is a
  player's first goal, not the match's first goal, and the two are different facts.
- Every number you write must appear in the sentences, written the same way. Never write a
  number, a count, an ordinal or a time in words unless that word is in the sentences.
- Name only the teams and players the sentences name.
- Never use the abbreviation {_BANNED}. A shot's value is "shot quality".
- Third person always. Never "we", "us", "our" or "ours": you are not on either side. Where a
  sentence is told from one side, keep that side first.
- Write in the language given. Keep it at most as long as the sentences together.

Do more than join the sentences: write it the way the register below would say it, with the
facts in the order that tells the moment best. Keep each label ("shot quality", "possession
share") next to its number.

Register:
"""


def instructions(depth: Depth) -> str:
    return INSTRUCTIONS + _REGISTERS[depth] + "\n"


def prompt(sentences: Sequence[str], lens: Lens) -> str:
    """What the model is shown: the spoken sentences and the lens's register, nothing more."""
    return json.dumps(
        {"depth": lens.depth.value, "language": lens.language, "sentences": list(sentences)},
        separators=(",", ":"),
        ensure_ascii=False,
    )


def write(
    sentences: Sequence[str], lens: Lens, names: Mapping[str, str], model: Proposer
) -> Written | None:
    """The model's words for `sentences` at `lens`'s register, or None if it gave none we keep.

    None for no sentences, without asking: there is nothing to word.
    """
    if not sentences:
        return None
    try:
        answer: Answer = model.propose(instructions(lens.depth), prompt(sentences, lens))
    except Exception as failure:  # any failure to answer is the same failure: L3's words
        logger.warning("writer: no answer for %s: %r", lens.lens_id, failure)
        return None
    try:
        text = _Response.model_validate_json(answer.text, strict=True).text.strip()
    except ValidationError as failure:
        logger.warning("writer: non-conforming answer for %s: %s", lens.lens_id, failure)
        return None
    untraced = untraceable(text, sentences, names, lens.language)
    if untraced is not None:
        logger.warning(
            "writer: dropped %s's text from %s: %s", lens.lens_id, answer.model, untraced
        )
        return None
    return Written(text, answer.model, f"{answer.model_version}+{PROMPT_VERSION}")


_NUMBER = re.compile(r"\d+(?:\.\d+)?(?:st|nd|rd|th)?")  # "2nd" is not "2"
_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")  # "Brack's" is "Brack" and "s"
_SIDE_VOICE = frozenset({"we", "us", "our", "ours", "ourselves"})
_SENTENCE_START = re.compile(r"(?:^|[.!?:]\s+)$")


def untraceable(
    text: str, sentences: Sequence[str], names: Mapping[str, str], language: str
) -> str | None:
    """What in `text` does not trace to `sentences`, or None if everything does.

    `names` is every team and player the match has, so naming one the sentences do not is
    caught; a capitalised word in mid-sentence that no sentence has is caught as a name too.
    """
    if not text:
        return "no text"
    given = " ".join(sentences)
    numbers = set(_NUMBER.findall(text)) - set(_NUMBER.findall(given))
    if numbers:
        return f"numbers {sorted(numbers)}"
    words = [w.lower() for w in _WORD.findall(text)]
    if _BANNED.lower() in words:
        return _BANNED
    if voice := _SIDE_VOICE.intersection(words):
        return f"a side's voice {sorted(voice)}"
    given_words = {w.lower() for w in _WORD.findall(given)}
    number_words = templates.number_words(language) or frozenset()
    if invented := number_words.intersection(words) - given_words:
        return f"number words {sorted(invented)}"
    named = {n for n in names.values() if n in given}
    allowed = {part for n in named for part in _WORD.findall(n)}
    unnamed = {part for n in names.values() if n not in named for part in _WORD.findall(n)}
    if others := (unnamed - allowed).intersection(_WORD.findall(text)):
        return f"names {sorted(others)}"  # a surname alone is still a name
    capitals = {w for w in _WORD.findall(given) if w[0].isupper()}
    for match in _WORD.finditer(text):
        word = match.group()
        if not word[0].isupper() or word in allowed or word in capitals:
            continue
        if not _SENTENCE_START.search(text[: match.start()]):
            return f"name {word!r}"
    return None
