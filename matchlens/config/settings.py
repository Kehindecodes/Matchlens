"""The only place in the codebase that reads the environment."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MATCHLENS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    # Match source and understanding
    frame_rate_hz: int = 2  # D13
    signal_window_ms: int = 300_000  # nominal; D15 clamps the effective window to the epoch
    signal_cadence_ms: int = 60_000  # one reading per team per signal, every match minute
    signal_confidence_k: int = 8  # samples at which a signal's confidence reaches one half
    baseline_k_minutes: int = 15
    baseline_k_minutes_after_break: int = 15  # D26: the same cold start, tuned separately
    match_seed: int = 1  # the demo match: the video and the tests run on this seed (F3)

    # Spotting (M1b). Calibrated on the demo match; the 30-60 moments band holds there and not on
    # every seed.
    spotter_z_threshold: float = 1.25  # |z_match| a tactical shift must reach
    spotter_confidence_floor: float = 0.3  # below this a large z is noise
    spotter_min_window_ms: int = 120_000  # a window this thin has not seen enough to judge
    spotter_cooldown_ms: int = 240_000  # M2: a series cannot fire a second shift inside this
    spotter_z_release: float = 1.0  # M2: |z_match| under this ends a shift; between is the same one
    spotter_chance_quality: float = 0.25  # shot quality a non-goal shot must reach
    importance_z_saturation: float = 3.0  # the |z| at which a shift's magnitude is full
    importance_prior_weight: float = 0.25  # how much of a shift's magnitude is z_prior's
    importance_goal: float = 1.0  # type weights: importance = weight * magnitude * confidence
    importance_chance: float = 0.8
    importance_tactical_shift: float = 0.7

    # Claims and the words they allow (D30). Standard values, not tuned per match. The big-chance
    # bar is `spotter_chance_quality` and plain interpretive wording `spotter_z_threshold`.
    claim_chance_window_ms: int = 600_000  # "big chances in the last ten minutes"
    claim_strong_z: float = 2.0  # |z_match| for strong words: "much harder", "by far"
    wording_chance_run: int = 3  # a run of big chances is spoken from the third
    wording_quick_attack_ms: int = 20_000  # ball won in open play to the shot
    wording_patient_passes: int = 10

    # Verification (A3)
    value_rel_tolerance: float = 1e-6  # Q35: counts are exact, every other value within this
    verifier_budget_ms: int = 500  # one claim's six checks, ~25x the slowest; then the rest fail

    # Lenses
    default_lens_id: str = "match_casual"
    team_result_boost: float = 1.25  # Q22: a goal or chance is worth this much more to a supporter
    team_focus_shift_damp: float = 0.5  # Q22: a shift by the supporter's own side, scaled by this
    default_language: str = "en"  # ISO 639-1

    # Delivery
    replay_speed: float = 25.0  # the in-process feed, until the pipeline sends over Service Bus
    max_replay_speed: float = 100.0  # the most the page may ask for (D3); above it is refused
    catchup_key_moments: int = 3  # D4, Q30: what a late joiner is told when nobody has scored
    overlay_ms_per_word: int = 250  # D5: an overlay stays up as long as it takes to read
    overlay_min_ms: int = 5_000
    overlay_max_ms: int = 12_000

    # Models
    model_name: str = ""
    foundry_endpoint: str = ""
    explainer_timeout_s: float = 20.0  # A2: the call itself gives up after this
    explainer_recent_ms: int = 60_000  # A2: how far back the moves shown to the model go
    explainer_deadline_ms: int = 15_000  # Q37, v1: cards wait this long for A2, from firing
    explainer_moment_types: tuple[str, ...] = ("goal", "chance")  # Q37: only these call A2
    explainer_concurrency: int = 4  # model calls in flight at once; moments are independent
    explainer_reasoning_effort: str = "low"  # D36: what a reasoning model spends per call
    explainer_cache_path: str = "matchlens/explanation/claims-cache.json"  # D36, empty: no cache

    # Infrastructure
    service_bus_connection: str = ""
    database_connection: str = ""
    appinsights_connection_string: str = Field(
        default="", validation_alias="APPLICATIONINSIGHTS_CONNECTION_STRING"
    )

    log_level: str = "INFO"


settings = Settings()
