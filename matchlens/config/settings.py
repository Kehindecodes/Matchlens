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
    spotter_chance_quality: float = 0.25  # shot quality a non-goal shot must reach
    importance_z_saturation: float = 3.0  # the |z| at which a shift's magnitude is full
    importance_prior_weight: float = 0.25  # how much of a shift's magnitude is z_prior's
    importance_goal: float = 1.0  # type weights: importance = weight * magnitude * confidence
    importance_chance: float = 0.8
    importance_tactical_shift: float = 0.7

    # Lenses
    default_lens_id: str = "match_casual"
    default_language: str = "en"  # ISO 639-1

    # Delivery
    replay_speed: float = 25.0  # the in-process feed, until the pipeline sends over Service Bus

    # Models
    model_name: str = ""
    foundry_endpoint: str = ""

    # Infrastructure
    service_bus_connection: str = ""
    database_connection: str = ""
    appinsights_connection_string: str = Field(
        default="", validation_alias="APPLICATIONINSIGHTS_CONNECTION_STRING"
    )

    log_level: str = "INFO"


settings = Settings()
