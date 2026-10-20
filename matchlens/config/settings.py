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
    match_seed: int = 1  # the demo match: the video and the tests run on this seed (F3)

    # Lenses
    default_lens_id: str = "match_casual"
    default_language: str = "en"  # ISO 639-1

    # Delivery
    replay_speed: float = 1.0  # the in-process feed, until the pipeline sends over Service Bus

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
