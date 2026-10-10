"""The only place in the codebase that reads the environment."""

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
    baseline_k_minutes: int = 15
    match_seed: int = 1  # the demo match: the video and the tests run on this seed (F3)

    # Lenses
    default_lens_id: str = "match_casual"

    # Models
    model_name: str = ""
    foundry_endpoint: str = ""

    # Infrastructure
    service_bus_connection: str = ""
    database_connection: str = ""

    log_level: str = "INFO"


settings = Settings()
