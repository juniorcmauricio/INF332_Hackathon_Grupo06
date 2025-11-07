# app/ai/hf_zero_shot.py
from __future__ import annotations
from typing import List, Tuple, Dict
import httpx
from ..config import settings
from .genre_mapper import TMDB_GENRES

def map_via_hf_api(mood: str, top_k: int = 2) -> List[Tuple[str, int]]:
    """
    Zero-shot via Hugging Face Inference API (no local ML deps).
    Returns a list of (genre_name, genre_id).
    """
    labels: List[str] = list(TMDB_GENRES.keys())
    model_id: str = settings.hf_model or "facebook/bart-large-mnli"
    token: str | None = settings.hf_api_key
    if not token:
        raise RuntimeError("HF_API_KEY not configured (HACK_HF_API_KEY)")

    url = f"https://api-inference.huggingface.co/models/{model_id}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    payload: Dict[str, object] = {
        "inputs": mood,
        "parameters": {"candidate_labels": labels, "multi_label": True},
    }

    with httpx.Client(timeout=settings.request_timeout_s) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

    pairs = list(zip(data["labels"], data["scores"]))  # type: ignore[index]
    pairs.sort(key=lambda x: x[1], reverse=True)
    top = pairs[:top_k]
    return [(name, TMDB_GENRES[name]) for name, _ in top]
