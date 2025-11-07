from __future__ import annotations
from typing import List, Tuple, Dict, Optional

TMDB_GENRES: Dict[str, int] = {
    "Action": 28, "Adventure": 12, "Animation": 16, "Comedy": 35, "Crime": 80,
    "Documentary": 99, "Drama": 18, "Family": 10751, "Fantasy": 14, "History": 36,
    "Horror": 27, "Music": 10402, "Mystery": 9648, "Romance": 10749,
    "Science Fiction": 878, "TV Movie": 10770, "Thriller": 53, "War": 10752, "Western": 37,
}

FALLBACK_MAP: Dict[str, List[str]] = {
    "feliz": ["Comedy", "Romance"],
    "happy": ["Comedy", "Romance"],
    "triste": ["Drama"],
    "sad": ["Drama"],
    "ansioso": ["Mystery", "Thriller"],
    "anxious": ["Mystery", "Thriller"],
    "focado": ["Documentary"],
    "focused": ["Documentary"],
    "bravo": ["Action"],
    "angry": ["Action"],
}

_zs: Optional[object] = None
_last_error: Optional[str] = None

def is_available() -> bool:
    """
    Returns True if the transformers zero-shot pipeline is available and loaded.
    """
    global _zs, _last_error
    if _zs is not None:
        return True
    try:
        from transformers import pipeline
        # smaller model for faster cold start
        _zs = pipeline("zero-shot-classification", model="valhalla/distilbart-mnli-12-3")
        return True
    except Exception as e:  # noqa: BLE001
        _last_error = str(e)
        return False

def last_error() -> Optional[str]:
    """
    Returns last initialization error, if any.
    """
    return _last_error

def fallback_genres_for(mood: str, top_k: int = 2) -> List[Tuple[str, int]]:
    """
    Static mapping fallback when transformers is not available.
    """
    if not mood:
        return []
    lower: str = mood.lower()
    names: List[str] = FALLBACK_MAP.get(lower, ["Comedy"])[:top_k]
    return [(name, TMDB_GENRES[name]) for name in names]

def map_mood_to_genres(mood: str, top_k: int = 2) -> List[Tuple[str, int]]:
    """
    Map a free-text `mood` to up to `top_k` TMDB genres using zero-shot.
    Falls back to static mapping if transformers is unavailable.
    """
    if is_available():
        assert _zs is not None  # for type checkers
        labels: List[str] = list(TMDB_GENRES.keys())
        res: Dict[str, List] = _zs(mood, candidate_labels=labels, multi_label=True)  # type: ignore[call-arg]
        pairs: List[Tuple[str, float]] = sorted(
            zip(res["labels"], res["scores"]), key=lambda x: x[1], reverse=True  # type: ignore[index]
        )[:top_k]
        return [(name, TMDB_GENRES[name]) for name, _ in pairs]
    return fallback_genres_for(mood, top_k)
