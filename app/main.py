from __future__ import annotations
from typing import Dict, Any, Annotated
from fastapi import FastAPI, Query, HTTPException
from tenacity import RetryError

from .config import settings
from .models import RecommendationList
from .services.recommendation_service import RecommendationService

from .ai.gemini_emotion import (
    map_via_gemini_api,
    get_last_error as get_gemini_error,
    get_last_http_status,
    get_last_raw_response,
    get_last_request_payload,
    get_model_name,
    get_api_version,
    get_available_models,
    get_used_model,
)


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
        "gemini_api_key_present": bool(settings.gemini_api_key),
        "gemini_model": get_model_name(),
        "gemini_api_version": get_api_version(),
        "gemini_model_configured": settings.gemini_model,
        "gemini_custom_prompt": bool(settings.gemini_prompt_template),
        "tmdb_region": settings.tmdb_region,
        "tmdb_include_providers": bool(settings.tmdb_include_providers),
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
                genres_ia = map_via_gemini_api(mood, 2)
                remote_ok = True
            except Exception:
                genres_ia = []
        else:  # off
            genres_ia = []

        genres_fb = fallback_genres_for(mood, 2)
        tmdb_try = await dbg_tmdb.discover_by_genres([35], seed=mood)

        raw_resp = get_last_raw_response()
        # Only show a compact snippet to avoid huge payloads in debug
        raw_snippet = None
        if isinstance(raw_resp, dict):
            # try to extract the first candidate text for quick inspection
            try:
                cand = raw_resp.get("candidates")
                if isinstance(cand, list) and cand:
                    content = cand[0].get("content") if isinstance(cand[0], dict) else None
                    parts = content.get("parts") if isinstance(content, dict) else None
                    if isinstance(parts, list) and parts and isinstance(parts[0], dict):
                        txt = parts[0].get("text", "")
                        raw_snippet = txt[:200]
            except Exception:  # noqa: BLE001
                raw_snippet = None

        return {
            "ai_mode": ai_mode,
            "local_available": local_available,
            "remote_ok": remote_ok,
            "ia_error": last_error() or get_gemini_error(),
            "gemini_http_status": get_last_http_status(),
            "gemini_request_payload": get_last_request_payload(),
            "gemini_raw_snippet": raw_snippet,
            "gemini_api_version": get_api_version(),
            "gemini_model_effective": get_used_model() or get_model_name(),
            "gemini_models_available": get_available_models()[:10],
            "genres_ia": genres_ia,
            "genres_fallback": genres_fb,
            "tmdb_sample_count": len(tmdb_try),
        }

    except RetryError as re:
        inner = re.last_attempt.exception()
        raise HTTPException(status_code=502, detail=f"{type(inner).__name__}: {inner}") from re
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e