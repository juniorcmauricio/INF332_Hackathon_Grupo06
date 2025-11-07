from __future__ import annotations
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict  # ⬅️ use SettingsConfigDict (v2 style)

class Settings(BaseSettings):
    """
    Centralized, typed configuration (12-factor).
    Values are read from environment and the .env file.
    """
    app_name: str = "Hackathon Movies API"
    request_timeout_s: float = 3.0

    # External provider (TMDB)
    movies_api_base: str = "https://api.themoviedb.org/3"
    movies_api_key: str = ""              # v4 bearer (unused for v3)
    tmdb_v3_key: Optional[str] = None     # ⬅️ your v3 key lives here

    # ⬇️ THIS is the important bit for pydantic-settings v2
    model_config = SettingsConfigDict(
        env_prefix="HACK_",   # reads HACK_TMDB_V3_KEY, etc.
        env_file="movieapi.env",      # load movieapi.env from project root
    )

settings: Settings = Settings()
