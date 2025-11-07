from __future__ import annotations
from typing import Dict, Any, Annotated
from fastapi import FastAPI, Query, HTTPException
from tenacity import RetryError

from .config import settings
from .models import RecommendationList
from .services.recommendation_service import RecommendationService

from .ai.hf_zero_shot import map_via_hf_api


# debug helpers
from .clients.tmdb import TMDBClient
from .ai.genre_mapper import (
    is_available,
    last_error,
    fallback_genres_for,
    map_mood_to_genres,
)


app: FastAPI = FastAPI(title=settings.app_name, version="0.1.0")
service: RecommendationService = RecommendationService()

@app.get("/health")
def health() -> Dict[str, str]:
    """Simple liveness probe."""
    print("TMDB v3 key present?", bool(settings.tmdb_v3_key and settings.tmdb_v3_key.strip()))
    print("TMDB base:", settings.movies_api_base)
    return {"status": "ok"}

MoodParam = Annotated[
    str,
    Query(
        ...,
        pattern=r"^[\w\sÀ-ÿ,.'!?-]{1,100}$",
        description="Texto/livre que representa o humor desejado (ex.: 'quero algo leve e inspirador')",
    ),
]

@app.get("/recommendations", response_model=RecommendationList)
async def recommendations(mood: MoodParam) -> RecommendationList:
    """
    Main endpoint: accepts a free-text mood and returns recommendations.
    """
    return await service.recommend_by_mood(mood)

dbg_tmdb: TMDBClient = TMDBClient()

@app.get("/_debug/config")
def debug_config() -> Dict[str, Any]:
    """Debug endpoint to show current configuration."""
    print("Debug config endpoint called")
    return {
        "ai_mode": settings.ai_mode,
        "hf_model": settings.hf_model,
        "hf_api_key_present": bool(settings.hf_api_key),
        "tmdb_v3_key_present": bool(settings.tmdb_v3_key),
    }

@app.get("/_debug/checks")
async def debug_checks(mood: str = "feliz") -> Dict[str, Any]:
    """
    Diagnostics that respect AI mode:
      - ai_mode: remote | local | off
      - local_available: only meaningful when ai_mode=local
      - remote_ok: True if remote call succeeded
    """
    print("DEBUG AI_MODE:", settings.ai_mode)
    try:
        ai_mode = (settings.ai_mode or "remote").lower()
        local_available = False
        remote_ok = False
        genres_ia = []

        if ai_mode == "local":
            local_available = is_available()
            genres_ia = map_mood_to_genres(mood, 2) if local_available else []
        elif ai_mode == "remote":
            try:
                genres_ia = map_via_hf_api(mood, 2)
                remote_ok = True
            except Exception:
                genres_ia = []
        else:  # off
            genres_ia = []

        genres_fb = fallback_genres_for(mood, 2)
        tmdb_try = await dbg_tmdb.discover_by_genres([35], seed=mood)

        return {
            "ai_mode": ai_mode,
            "local_available": local_available,
            "remote_ok": remote_ok,
            "ia_error": last_error(),
            "genres_ia": genres_ia,
            "genres_fallback": genres_fb,
            "tmdb_sample_count": len(tmdb_try),
        }

    except RetryError as re:
        inner = re.last_attempt.exception()
        raise HTTPException(status_code=502, detail=f"{type(inner).__name__}: {inner}") from re
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e