from __future__ import annotations
from typing import List
from cachetools import TTLCache
from ..models import Recommendation, RecommendationList
from ..clients.tmdb import TMDBClient
from ..ai import genre_mapper, gemini_emotion  # import modules, not functions to avoid circular imports
from ..config import settings

tmdb: TMDBClient = TMDBClient()
cache: TTLCache[str, RecommendationList] = TTLCache(maxsize=512, ttl=600)

class RecommendationService:
    """
    Business service that coordinates AI mapping, TMDB calls and caching.
    """

    async def recommend_by_mood(self, mood: str) -> RecommendationList:
        """
        Recommend movies given a free-text mood.
        """
        seed: str = mood.lower().strip()
        key: str = f"recs:{seed}"
        if key in cache:
            return cache[key]

        items: List[Recommendation] = []
        try:
            mode = (settings.ai_mode or "remote").lower()
            if mode == "off":
                top = genre_mapper.fallback_genres_for(mood, top_k=2)
            elif mode == "remote":
                try:
                    top = gemini_emotion.map_via_gemini_api(mood, top_k=2)   # 🚀 remote, using Gemini
                except Exception:
                    top = genre_mapper.fallback_genres_for(mood, top_k=2)    # graceful fallback
            else:  # "local"
                if genre_mapper.is_available():
                    top = genre_mapper.map_mood_to_genres(mood, top_k=2)     # local transformers (optional)
                else:
                    top = genre_mapper.fallback_genres_for(mood, top_k=2)
            genre_ids: List[int] = [gid for _, gid in (top or [])] or [35]  # default to Comedy
            rows = await tmdb.discover_by_genres(genre_ids, seed=seed)
            if not rows:
                rows = await tmdb.search_by_mood(mood)
            include_prov: bool = bool(settings.tmdb_include_providers)
            for r in rows:
                providers = None
                mid = r.get("id")
                # Normalize id to int when possible (TMDB returns int, but be defensive)
                if include_prov:
                    mid_int = None
                    if isinstance(mid, int):
                        mid_int = mid
                    elif isinstance(mid, str):
                        try:
                            mid_int = int(mid)
                        except Exception:
                            mid_int = None
                    if isinstance(mid_int, int):
                        try:
                            providers = await tmdb.get_watch_providers(mid_int)
                        except Exception:
                            providers = None  # silent fail, keep rec resilient
                items.append(Recommendation(title=str(r["title"]), source="TMDB", score=float(r["score"]), providers=providers))
        except Exception as _e:  # noqa: BLE001
            # keep demo resilient: return a single safe item if everything fails
            items.append(Recommendation(title=f"Fallback pick for '{mood}'", source="fallback", score=0.5))

        result: RecommendationList = RecommendationList(items=items)
        cache[key] = result
        return result
