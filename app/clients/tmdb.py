from __future__ import annotations
from typing import List, Dict, Any, Optional
import hashlib
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter
from ..config import settings

def _pick_page(seed: str, max_pages: int = 5) -> int:
    """
    Deterministically choose a page number (1..max_pages) from a seed string.
    """
    h: str = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return (int(h[:8], 16) % max_pages) + 1

def _pick_sort(seed: str) -> str:
    """
    Deterministically choose a sort criterion from a seed string.
    """
    return "vote_average.desc" if ord(seed[0]) % 2 == 0 else "popularity.desc"

class TMDBClient:
    """
    Minimal typed adapter for TMDB (v3 key as query param).
    """

    def __init__(self) -> None:
        self.base: str = settings.movies_api_base.rstrip("/")
        self.timeout: httpx.Timeout = httpx.Timeout(settings.request_timeout_s)
        self.v3_key: str = (settings.tmdb_v3_key or "").strip()

    def _headers(self) -> Dict[str, str]:
        """
        Common headers for all requests.
        """
        return {"Accept": "application/json"}

    def _params(self) -> Dict[str, str]:
        """
        Authentication parameters for v3 API key.
        """
        return {"api_key": self.v3_key} if self.v3_key else {}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(0.1, 0.6))
    async def search_by_mood(self, mood: str) -> List[Dict[str, Any]]:
        """
        Fallback text search when genre-based discover returns empty.
        """
        q: str = mood
        async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers()) as client:
            params: Dict[str, Any] = {"query": q, "include_adult": "false", "language": "pt-BR", "page": 1}
            params.update(self._params())
            r: httpx.Response = await client.get(f"{self.base}/search/movie", params=params)
            if r.status_code >= 400:
                raise RuntimeError(f"/search/movie {r.status_code} :: {str(r.url)} :: {r.text[:300]}")
            payload: Dict[str, Any] = r.json()
            results: List[Dict[str, Any]] = payload.get("results", [])

        out: List[Dict[str, Any]] = []
        for m in results[:10]:
            title: str = m.get("title") or m.get("name") or "Desconhecido"
            vote: float = float(m.get("vote_average") or 0.0)
            score: float = max(0.0, min(1.0, vote / 10.0))
            out.append({"title": title, "score": score, "id": m.get("id")})
        return out

    @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(0.1, 0.6))
    async def discover_by_genres(self, genre_ids: List[int], seed: str) -> List[Dict[str, Any]]:
        """
        Genre-first discovery with deterministic diversity (page/sort).
        """
        gid: str = ",".join(str(g) for g in genre_ids)
        page: int = _pick_page(seed, max_pages=5)
        sort_by: str = _pick_sort(seed)
        async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers()) as client:
            params: Dict[str, Any] = {
                "with_genres": gid,
                "sort_by": sort_by,
                "vote_count.gte": 200,
                "language": "pt-BR",
                "page": page,
            }
            params.update(self._params())
            r: httpx.Response = await client.get(f"{self.base}/discover/movie", params=params)
            if r.status_code >= 400:
                raise RuntimeError(f"/discover/movie {r.status_code} :: {str(r.url)} :: {r.text[:300]}")
            payload: Dict[str, Any] = r.json()
            results: List[Dict[str, Any]] = payload.get("results", [])[:10]

        out: List[Dict[str, Any]] = []
        for m in results:
            title: str = m.get("title") or m.get("name") or "Desconhecido"
            vote: float = float(m.get("vote_average") or 0.0)
            score: float = max(0.0, min(1.0, vote / 10.0))
            out.append({"title": title, "score": score, "id": m.get("id")})
        return out

    @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(0.1, 0.6))
    async def get_watch_providers(self, movie_id: int) -> List[str]:
        """Fetch streaming providers for a movie ID (TMDB watch/providers endpoint)."""
        region: str = (settings.tmdb_region or "US").upper()
        async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers()) as client:
            params: Dict[str, Any] = {}
            params.update(self._params())
            r: httpx.Response = await client.get(f"{self.base}/movie/{movie_id}/watch/providers", params=params)
            if r.status_code >= 400:
                raise RuntimeError(f"/movie/{movie_id}/watch/providers {r.status_code} :: {str(r.url)} :: {r.text[:200]}")
            data: Dict[str, Any] = r.json() or {}
        results: Dict[str, Any] = data.get("results", {}) if isinstance(data, dict) else {}
        entry: Dict[str, Any] = results.get(region) or results.get("US") or {}
        flat: List[str] = []
        def _extract(list_name: str) -> None:
            arr = entry.get(list_name)
            if isinstance(arr, list):
                for prov in arr:
                    if isinstance(prov, dict):
                        name = prov.get("provider_name") or prov.get("display_priority")
                        if isinstance(name, str):
                            flat.append(name)
        for section in ["flatrate", "rent", "buy", "ads", "free"]:
            _extract(section)
        # de-duplicate preserving order
        seen = set()
        ordered: List[str] = []
        for p in flat:
            if p not in seen:
                seen.add(p)
                ordered.append(p)
        return ordered[:8]
