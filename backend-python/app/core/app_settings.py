"""Loads environment-backed settings for the API process."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """
    Simple env reader for the backend.

    Casual: grabs config from env vars so Docker and local venv behave the same.

    Reads `APP_*` variables (and `.env` when present) so the same settings work
    inside Docker Compose and in a local virtualenv without hard-coding paths
    or host-specific values.
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    api_title: str = "Corn Ethanol Arb Monitor API"
    api_version: str = "0.1.0"
    eia_api_key: str = ""
    admin_token: str = ""
    duckdb_path: str = "data/ethanol_dashboard.duckdb"
    crush_model_path: str = "../config/crush_model.json"
