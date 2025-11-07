from __future__ import annotations
from typing import Dict, Any, Annotated
from fastapi import FastAPI, Query, HTTPException
from tenacity import RetryError

from .config import settings
from .models import RecommendationList
from .services.recommendation_service import RecommendationService

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

@app.get("/_debug/checks")
async def debug_checks(mood: str = "feliz") -> Dict[str, Any]:
    """
    Diagnostics: shows AI availability, fallback genres and TMDB reachability.
    """
    try:
        ia_ok: bool = is_available()
        genres_ia = map_mood_to_genres(mood, 2) if ia_ok else []
        genres_fb = fallback_genres_for(mood, 2)
        tmdb_try = await dbg_tmdb.discover_by_genres([35], seed=mood)  # "proof of life" query

        return {
            "ia_available": ia_ok,
            "ia_error": last_error(),
            "genres_ia": genres_ia,
            "genres_fallback": genres_fb,
            "tmdb_sample_count": len(tmdb_try),
        }

    except RetryError as re:
        inner = re.last_attempt.exception()
        raise HTTPException(status_code=502, detail=f"{type(inner).__name__}: {inner}") from re
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e
