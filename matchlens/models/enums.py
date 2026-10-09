"""Closed sets, named and valued as in docs/DATA-MODEL.md "Enumerated types".

Closed sets are enums, not strings: the verifier's checks depend on these being exact, and a
typo in a string field fails silently. Later groups add their enums here.
"""

from enum import StrEnum


class Phase(StrEnum):
    IN_PLAY = "in_play"
    STOPPED = "stopped"
    SET_PIECE = "set_piece"


class Action(StrEnum):
    PASS = "pass"
    CARRY = "carry"
    SHOT = "shot"
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    CLEARANCE = "clearance"
    BLOCK = "block"
    AERIAL_DUEL = "aerial_duel"
    SAVE = "save"
    FOUL = "foul"
    THROW_IN = "throw_in"
    CORNER = "corner"
    GOAL_KICK = "goal_kick"
    FREE_KICK = "free_kick"
    PENALTY = "penalty"
    # Match events (D16): they change the roster or the clock, and carry no positions.
    SUBSTITUTION = "substitution"
    RED_CARD = "red_card"
    YELLOW_CARD = "yellow_card"
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"


class Outcome(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    BLOCKED = "blocked"
    GOAL = "goal"
    SAVED = "saved"
    OFF_TARGET = "off_target"
    WON = "won"
    LOST = "lost"
    OUT_OF_PLAY = "out_of_play"


class BodyPart(StrEnum):
    LEFT_FOOT = "left_foot"
    RIGHT_FOOT = "right_foot"
    HEAD = "head"
    OTHER = "other"


class RefKind(StrEnum):
    TEAM = "team"
    PLAYER = "player"
    EVENT = "event"
    READING = "reading"
    RUN = "run"  # not built in v1; kept so the set matches the data model
    MOMENT = "moment"
    RENDITION = "rendition"
    LENS = "lens"
