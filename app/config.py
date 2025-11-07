from __future__ import annotations
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict  # ⬅️ use SettingsConfigDict (v2 style)

class Settings(BaseSettings):
    """
    Centralized, typed configuration (12-factor).
    Values are read from environment and the .env file.
    """
    app_name: str = "Hackathon Movies API"
    request_timeout_s: float = 15.0

    # External provider (TMDB)
    movies_api_base: str = "https://api.themoviedb.org/3"
    movies_api_key: str = ""              # v4 bearer (unused for v3)
    tmdb_v3_key: Optional[str] = None     # ⬅️ your v3 key lives here

    # AI configuration
    ai_mode: str | None = "remote"     # remote | local | off
    # Gemini
    gemini_api_key: str | None = None
    gemini_model: Optional[str] = None  # e.g., 'gemini-pro' (v1) or 'gemini-1.5-flash' (v1beta)
    # Optional custom prompt template for Gemini. Use placeholders: {mood}, {labels}, {top_k}
    gemini_prompt_template: Optional[str] = None
    # Watch providers (TMDB)
    tmdb_region: Optional[str] = "BR"  # ISO 3166-1 code defaulting to Brazil
    tmdb_include_providers: bool = False  # enable to fetch streaming providers per title


    # ⬇️ THIS is the important bit for pydantic-settings v2
    model_config = SettingsConfigDict(
        env_prefix="HACK_",   # reads HACK_TMDB_V3_KEY, etc.
        env_file="movieapi.env",      # load movieapi.env from project root
    )

settings: Settings = Settings()
