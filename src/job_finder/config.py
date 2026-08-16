"""Env-backed configuration, loaded once at import time."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Prefer `.env` over OS env vars. Windows shells often leak stale
        # empty-string exports (e.g. `ANTHROPIC_API_KEY=`) that would otherwise
        # silently clobber a valid value from .env.
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)

    # --- Database ---
    database_url: str = Field(
        default="postgresql://jfb:jfb_dev@localhost:5432/jfb",
        description="psycopg-compatible URL",
    )

    # --- LLM / embeddings (needed Sprint 2+) ---
    anthropic_api_key: str = ""
    ollama_host: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text:v1.5"

    # --- Monitoring / notifications (optional) ---
    sentry_dsn: str = ""
    resend_api_key: str = ""
    resend_from: str = "Job Finder Bot <onboarding@resend.dev>"
    resend_to: str = ""

    # --- Aggregator API keys (optional) ---
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    jooble_api_key: str = ""

    # --- HTTP / logging ---
    http_timeout_s: float = 30.0
    http_user_agent: str = "job-finder-bot/0.1 (personal use)"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    # --- Drafter ---
    # Default drafting mode for the queue button on /top + /posting:
    #   tailor — model paraphrases bullets to match the posting (original)
    #   curate — model only selects sections + pulls VERBATIM emphasis quotes
    # See drafter/prompts.py for the full contract per mode.
    draft_mode_default: Literal["tailor", "curate"] = "curate"

    # --- Paths ---
    artifacts_dir: Path = ROOT_DIR / "artifacts"
    resumes_dir: Path = ROOT_DIR / "resumes"


settings = Settings()

# Ensure directories exist
settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
settings.resumes_dir.mkdir(parents=True, exist_ok=True)
