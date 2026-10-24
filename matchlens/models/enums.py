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
    ADDED_TIME_ANNOUNCED = "added_time_announced"


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


# --- group B: derived understanding --------------------------------------------------------------


class Zone(StrEnum):
    DEFENSIVE_THIRD = "defensive_third"
    MIDDLE_THIRD = "middle_third"
    FINAL_THIRD = "final_third"


class PossessionOutcome(StrEnum):
    SHOT = "shot"
    TURNOVER = "turnover"
    FOUL = "foul"
    OUT_OF_PLAY = "out_of_play"
    PERIOD_END = "period_end"  # the half ended with the ball live (Q12)


class Signal(StrEnum):
    TERRITORY = "territory"
    POSSESSION_CONTROL = "possession_control"
    PRESSING_INTENSITY = "pressing_intensity"
    CHANCE_QUALITY = "chance_quality"
    LINE_HEIGHT = "line_height"


class Trend(StrEnum):
    RISING = "rising"
    FALLING = "falling"
    STEADY = "steady"


class EpochTrigger(StrEnum):
    GOAL = "goal"
    RED_CARD = "red_card"
    HALF_TIME = "half_time"


# --- group C: editorial output -------------------------------------------------------------------
# `Verdict` and `CheckName` belong to the `Claim` / six-check design and land with it.


class MomentType(StrEnum):
    GOAL = "goal"
    CHANCE = "chance"
    TACTICAL_SHIFT = "tactical_shift"
    MILESTONE = "milestone"
    PATTERN = "pattern"


class Metric(StrEnum):
    """What a claim's operand measures (D30). Every value is recountable from cited rows."""

    GOALS = "goals"
    SHOT_QUALITY = "shot_quality"
    CHANCES = "chances"
    BUILD_UP_PASSES = "build_up_passes"
    TERRITORY = "territory"
    POSSESSION_CONTROL = "possession_control"
    PRESSING_INTENSITY = "pressing_intensity"
    CHANCE_QUALITY = "chance_quality"


class ClaimType(StrEnum):
    DESCRIPTIVE = "descriptive"
    COMPARATIVE = "comparative"
    INTERPRETIVE = "interpretive"


class SuppressionReason(StrEnum):
    """Declared in evaluation order: when several apply, the first one listed wins (D14)."""

    OUT_OF_SCOPE = "out_of_scope"
    MUTED = "muted"
    DEGRADED = "degraded"
    VERIFICATION_FAILED = "verification_failed"
    CLAIMS_FILTERED_OUT = "claims_filtered_out"
    BELOW_THRESHOLD = "below_threshold"
    RATE_LIMITED = "rate_limited"


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class CheckName(StrEnum):
    """The six checks. Exactly these, and all of them run for every claim."""

    CITATION = "citation"
    TEMPORAL = "temporal"
    ENTITY = "entity"
    VALUE = "value"
    ENTAILMENT = "entailment"
    COVERAGE = "coverage"


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"  # ran, nothing to judge: e.g. entity for a team subject


# --- group D: delivery and configuration ---------------------------------------------------------


class Scope(StrEnum):
    MATCH = "match"
    TEAM = "team"
    PLAYER = "player"


class Depth(StrEnum):
    CASUAL = "casual"
    ENGAGED = "engaged"
    ANALYST = "analyst"


class DetailLevel(StrEnum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    FULL = "full"


class ProducerActionType(StrEnum):
    SUPPRESS = "suppress"
    HOLD = "hold"
    RELEASE = "release"
    PIN = "pin"


class OverlayTemplate(StrEnum):
    LOWER_THIRD = "lower_third"
    STAT_BAR = "stat_bar"
    TEAM_CARD = "team_card"
