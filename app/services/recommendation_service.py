from __future__ import annotations
from typing import List
from cachetools import TTLCache
from ..models import Recommendation, RecommendationList
from ..clients.tmdb import TMDBClient
from ..ai.genre_mapper import map_mood_to_genres, is_available, fallback_genres_for

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
            top = map_mood_to_genres(mood, top_k=2) if is_available() else fallback_genres_for(mood, top_k=2)
            genre_ids: List[int] = [gid for _, gid in (top or [])] or [35]  # default to Comedy

            rows = await tmdb.discover_by_genres(genre_ids, seed=seed)
            if not rows:
                rows = await tmdb.search_by_mood(mood)

            for r in rows:
                items.append(Recommendation(title=str(r["title"]), source="TMDB", score=float(r["score"])))
        except Exception as _e:  # noqa: BLE001
            # keep demo resilient: return a single safe item if everything fails
            items.append(Recommendation(title=f"Fallback pick for '{mood}'", source="fallback", score=0.5))

        result: RecommendationList = RecommendationList(items=items)
        cache[key] = result
        return result
