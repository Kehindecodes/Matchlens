"""A4: a model rewriting one lens's spoken claims in that lens's register (L0).

The model is shown the sentences L3 would speak for this lens, one per claim, and the lens's
depth and language. Nothing else: not the moment, not its importance, not another lens's claims,
not the claims L3 would leave unspoken. The headline and the opening line stay the template's
(Q38: 1A), and so do the score a goal left and who saved or blocked a shot, so the model only
ever words how a moment came about.

What it answers is checked before it can reach a card (Q38: 2A), because nothing downstream will
(D22): every number, every number word and every name it writes must already be in the sentences
it was given, it never names shot quality by its abbreviation (invariant 12), it never speaks
as a side, "we" or "our" (D31), and no sentence of it is a name alone, which says nothing: told
never to say what happened, a model once cut "Saved by X" to "X.". An answer that fails any of
these, or does not parse,
or never comes, gives no text, and the card keeps L3's words. It is also a failure the
ladder scores (A5): one takes the writer down until it answers well twice in a row.

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

from matchlens.explanation import Answer, Failure, Proposer
from matchlens.models import Depth, Lens
from matchlens.rendering import templates

logger = logging.getLogger(__name__)

PROMPT_VERSION = "writer-9"  # bump by hand whenever the instructions or the prompt change

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
        "Casual: a viewer who wants to know what is going on, in plain words. Short, warm, no "
        "statistics vocabulary. Never a number, as digits or in words."
    ),
    Depth.ENGAGED: (
        "Engaged: a viewer who follows the game closely. Sounds like a commentator's aside, "
        "not a list: one short sentence, every number kept, no jargon beyond the sentences' own."
    ),
    Depth.ANALYST: (
        "Analyst: a viewer who wants the mechanism and the numbers, in as few words as "
        "possible: a label and its figures, not a paragraph. Every number exactly as given, "
        "each with its label."
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
- This is an overlay on a live picture, up for a few seconds, and the viewer is watching the
  match: they have seen the goal or the shot, and a headline above your words already says what
  it did. Never say that it happened, and never repeat the headline. Say only what the
  sentences add to it, as one sentence of at most 20 words. A sentence that is already short
  and natural is returned as it is. Never answer with an empty passage.
- Who scored, set it up, saved or blocked it is something the sentences add. Keep what the
  person did with their name ("Ivo Marr with the goal", "saved by Ivo Marr"), never the name
  alone: "Ivo Marr." on its own says nothing.

How to write it. These are freedoms, and the rules above still bind every one of them.
- Do not just join the sentences. Rewrite them as connected prose in the register below.
- Merge facts into fewer sentences, reorder them so the moment reads best, and link them with
  plain connectives: "and", "after", "with", "as", "while", a colon or a dash.
- Drop the sentences' scaffolding where the prose already carries it: "Scorer: X, his first of
  the match" can become "X's first of the match", and "X goals so far: 1" can join the score.
- Once a player is named, "he" and "his" may refer back to him; once a team is named, "they".
- Keep each label ("shot quality", "possession share", "pressing intensity") beside its
  number, so a reader always knows what a number measures.
- Still no adjective or verb that judges: not "dominant", "clinical", "lucky", "deserved",
  "against the run of play". Say what happened, not how good it was.
- Every sentence you write must be grammatical English on its own. Never paste a fragment
  such as "goals so far: 1" into the middle of a sentence; say it as prose instead.
- Say each fact once. If two sentences say the same thing, for instance both call the shot a
  big chance, say it once. If two sentences share a label, say the label once and give both
  figures under it. Every number still appears.
- Do not open on a stock formula such as "X had a clear chance and did not take it" or "X took
  a shot rated as a chance". Do not begin two sentences in a row with the same word. Once a
  team is named, "they" or "their" is better than the name again.
- Read it back as a commentator would say it. If it sounds like a form being filled in, merge
  and reorder until it does not.

An example, with invented teams, players and numbers that are not this match's:
  analyst, from ["Ball won in own third.", "Quick attack: 5 passes in 12 s.", "Shot from 14.2 m."]:
  "Won in their own third, 5 passes in 12 s, a shot from 14.2 m."
  engaged, from ["Calder trail 1–2."]: "Calder now trail 1–2."
  engaged, from ["The third big chance for Ostby in ten minutes.", "A big chance."]:
  "That is Ostby's third big chance in ten minutes." (the second sentence added nothing)
  casual, from ["Won back deep in their own half."]: "Won back deep in their own half."
  (one short fact that already reads well is left alone)
The example shows the kind of rewriting wanted; its words are not to be reused.

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
) -> Written | Failure | None:
    """The model's words for `sentences` at `lens`'s register, or a `Failure` if it gave none
    we keep: no answer, one that does not parse, or one the check drops.

    None for no sentences, without asking: there is nothing to word, and nothing to score.
    """
    if not sentences:
        return None
    try:
        answer: Answer = model.propose(instructions(lens.depth), prompt(sentences, lens))
    except Exception as failure:  # any failure to answer is the same failure: L3's words
        logger.warning("writer: no answer for %s: %r", lens.lens_id, failure)
        return Failure(f"no answer: {failure!r}")
    try:
        text = _Response.model_validate_json(answer.text, strict=True).text.strip()
    except ValidationError as failure:
        logger.warning("writer: non-conforming answer for %s: %s", lens.lens_id, failure)
        return Failure("an answer that does not parse")
    untraced = untraceable(text, sentences, names, lens.language) or name_alone(text, names)
    if untraced is not None:
        logger.warning(
            "writer: dropped %s's text from %s: %s", lens.lens_id, answer.model, untraced
        )
        return Failure(f"text that does not trace: {untraced}")
    return Written(text, answer.model, f"{answer.model_version}+{PROMPT_VERSION}")


_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+")


def name_alone(text: str, names: Mapping[str, str]) -> str | None:
    """A sentence of `text` that is only a team's or a player's name, or None if there is none."""
    known = set(names.values())
    for said in _SENTENCE_END.split(text):
        bare = said.strip().rstrip(".!?;,").strip()
        if bare in known:
            return f"a name alone {bare!r}"
    return None


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
    words = [word.lower() for word in _WORD.findall(text)]
    if _BANNED.lower() in words:
        return _BANNED
    if voice := _SIDE_VOICE.intersection(words):
        return f"a side's voice {sorted(voice)}"
    given_words = {word.lower() for word in _WORD.findall(given)}
    number_words = templates.number_words(language) or frozenset()
    if invented := number_words.intersection(words) - given_words:
        return f"number words {sorted(invented)}"
    named = {name for name in names.values() if name in given}
    allowed = {part for name in named for part in _WORD.findall(name)}
    unnamed = {part for name in names.values() if name not in named for part in _WORD.findall(name)}
    if others := (unnamed - allowed).intersection(_WORD.findall(text)):
        return f"names {sorted(others)}"  # a surname alone is still a name
    capitals = {word for word in _WORD.findall(given) if word[0].isupper()}
    for match in _WORD.finditer(text):
        word = match.group()
        if not word[0].isupper() or word in allowed or word in capitals:
            continue
        if not _SENTENCE_START.search(text[: match.start()]):
            return f"name {word!r}"
    return None
